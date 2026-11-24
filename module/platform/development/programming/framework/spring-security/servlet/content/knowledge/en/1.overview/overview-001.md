# Spring Security in Servlet Applications: Scope and Problems to Solve

## 1. What Does This Lesson Answer?

In a Java application running on the **Servlet stack** (for example, Spring Boot using Spring MVC and Tomcat), every HTTP request can reach controllers, services, and data. Without a protection layer, the application struggles to consistently answer key questions: *Who is calling? What are they allowed to do? How is that identity maintained across requests? How can a malicious request be blocked before business logic runs?*

**Spring Security** is a security framework integrated into Spring that provides authentication, authorization, and common web defense layers. For Servlets, the most important integration point is the **Servlet Filter chain** wrapping request processing. Spring Security does not automatically turn every application into a completely secure system: authorization policies, data design, secret protection, infrastructure configuration, and testing remain the application's responsibility.

After this lesson, you should be able to:

- Distinguish between authentication, authorization, and HTTP request protection; identify the responsibilities of Spring Security versus the Servlet container and the business layer.
- Explain the request path through `DelegatingFilterProxy`, `FilterChainProxy`, and `SecurityFilterChain` to Spring MVC.
- Recognize common concerns: public/private endpoints, role-based permissions, login sessions, CSRF, CORS, 401/403 handling, and configuring multiple filter chains.
- Set up a minimal protection policy for a Spring Boot Servlet application, while understanding the limitations of the example.

## 2. Scope of Spring Security on the Servlet Stack

The Servlet container (Tomcat, Jetty...) accepts HTTP connections, executes Servlet Filters, and dispatches to a servlet, typically Spring MVC's `DispatcherServlet`. Spring Security registers a bridge filter with the container; the security filters process the request **before** it reaches the controller along the normal path. Therefore, a policy can be applied uniformly across many endpoints without rewriting authentication logic in each controller.

Typical responsibilities:

| Concern | Spring Security Support | Application Must Still Decide |
| --- | --- | --- |
| **Authentication**: who is sending the request? | Login mechanisms, HTTP Basic, bearer token integration, `AuthenticationManager`, `AuthenticationProvider`, `SecurityContext` | Identity source, account policy, credential lifecycle |
| **Authorization**: what is that user allowed to do? | Path/method-based request rules, roles/authorities, method security when enabled | Real business permissions, resource ownership, tenant isolation, preventing cross-data access |
| **Session and security context** | Reading/writing security context per request, session support, session fixation protection for applicable flows | Choosing session vs. token, expiration, logout, revocation, and storage policy |
| **HTTP protection** | CSRF protection, security headers, CORS integration support, handling rejected requests | Proper configuration per frontend/API, TLS, cookies, reverse proxy, rate limiting |
| **Security errors** | Translating authentication/authorization errors into challenges, redirects, or HTTP 401/403 depending on configuration | API error format, safe error messages, observability, and auditing |

**Important boundary:** Spring Security does not replace HTTPS/TLS, firewalls/WAFs, input validation, parameterized SQL, output encoding against XSS, accurate CORS policies, secret management, brute-force protection/rate limiting, object-level authorization audits, or library vulnerability patching. Those measures must work together with the framework.

Servlet security and WebFlux security are also **two different models**. This section discusses `HttpSecurity`, `SecurityFilterChain`, `SecurityContextHolder`, and Servlet Filters; it does not apply verbatim to `ServerHttpSecurity`/`SecurityWebFilterChain` of the reactive stack.

## 3. Where Does Spring Security Sit in the Request Flow?

High-level path:

```text
HTTP client
    |
Servlet container (Tomcat/Jetty)
    |
DelegatingFilterProxy ("springSecurityFilterChain")
    |
FilterChainProxy
    |
    +-- selects the first SecurityFilterChain matching the request
           |
           +-- security filters in framework-managed order
           |      (context, CSRF, authentication, exception,
           |       authorization... depending on configuration)
           |
           +-- continues the Servlet filter chain
                    |
               DispatcherServlet (Spring MVC)
                    |
               Controller -> Service -> Data
```

- **`DelegatingFilterProxy`**: a `javax/jakarta.servlet.Filter` bridge registered in the servlet container; it looks up a Spring bean typically named `springSecurityFilterChain` and delegates processing to that bean. On Spring Framework 6/Spring Boot 3, the Servlet API uses the `jakarta.servlet` namespace.
- **`FilterChainProxy`**: the central Spring bean containing one or more `SecurityFilterChain` instances. It selects the **first chain whose matcher matches** the request. Therefore, the order of chains matters when configuring multiple policies.
- **`SecurityFilterChain`**: a list of security filters for a group of requests. Each filter performs a dedicated job, such as loading the security context, handling authentication mechanisms, CSRF, translating exceptions, and checking permissions. The exact list and order depend on configuration/version; do not assume every request passes through the exact same set of filters.
- **Spring MVC/controller**: runs only when the request passes through the security layer. However, business logic must still enforce data-level permission checks when URL rules are not expressive enough.

Spring Security filters are **Servlet Filters**, not Spring MVC `HandlerInterceptor`s. Because filters sit at a lower HTTP layer, they can handle even requests not mapped to any controller. Using `permitAll()` on a route only bypasses the corresponding *authorization* requirement; the request may still pass through other security filters.

### An Authentication and Authorization Cycle

1. A request arrives, and the framework sets up or restores `SecurityContext` according to the configuration.
2. If the request carries credentials and the corresponding mechanism is enabled, the authentication filter asks `AuthenticationManager`/`AuthenticationProvider` to verify the credentials. A successful result is an authenticated `Authentication` containing the principal and authorities.
3. For stateful applications, the context can be saved to an appropriate store (often involving the HTTP session); for bearer token APIs, authentication is usually established from the token on each request. Do not assume both models behave the same way.
4. Upon reaching the permission check point, Spring Security evaluates `Authentication` and the `AuthorizationManager` policy to allow or deny.
5. At the end of the request, the framework clears the security context from the thread's execution context according to its mechanism to prevent identity leakage to another request.

By default, `SecurityContextHolder` uses a thread-bound strategy in the Servlet model. When offloading work to another thread or handling asynchronous processing manually, do **not** assume the context automatically propagates; use a context propagation mechanism supported by Spring Security or a clear separation design.

## 4. Six Core Problem Groups and the Right Way to Think About Them

### 4.1. Who Is Calling? — Authentication

An **unauthenticated** request typically has an anonymous context or lacks a trusted principal. An **authenticated** request contains an `Authentication` accepted by an appropriate mechanism. Authentication can be based on form login + session, HTTP Basic, bearer token, SSO/OAuth2 Login, or a custom mechanism; choosing one depends on the client type and trust model.

For example, with HTTP Basic, the client sends a Base64-encoded username/password in the `Authorization` header **on every request**. Base64 is not security encryption; HTTPS is always required in real environments. With form login, the application typically authenticates once and stores session state; the session cookie becomes sensitive data that must be protected.

Passwords must be stored as an **appropriate salted hash with computational cost** (for example, BCrypt or an equivalent encoder mechanism)—never store plaintext and never invent your own hashing algorithm. Spring Security provides `PasswordEncoder`; it does not replace defining registration policies, account locking, MFA, or credential lifecycles.

### 4.2. What Are They Allowed to Do? — Authorization

Successful login does **not** mean having permission to view or modify all data. Authorization has multiple levels:

- **Request level**: `GET /public` is open; `GET /profile` requires login; `/admin/**` requires administrative rights.
- **Method level**: `@PreAuthorize` can protect service methods after enabling `@EnableMethodSecurity`. Annotations do not work automatically just because the security starter is present.
- **Object/tenant level**: user A can only view A's invoices; this check usually requires domain-specific queries/conditions, such as `invoice.ownerId == currentUserId`. `hasRole("USER")` does not solve data ownership.

A `GrantedAuthority` is an actual permission string. By default convention, `hasRole("ADMIN")` looks for the authority `ROLE_ADMIN`; `hasAuthority("invoice:read")` matches that exact authority. Roles and permissions should not be conflated merely because of similar naming.

**Reasonable default policy:** explicitly permit only designated public routes, require authentication/authorization for the rest, and have a clear catch-all rule. If multiple custom chains exist and no chain matches a request, that request might go unprotected by Spring Security: this is a configuration bug worth checking.

### 4.3. How Is Identity Maintained? — Sessions, Tokens, and Logout

- **Session-based web app**: the server stores state associated with a session ID; the browser sends the session cookie. Requires appropriate `Secure`, `HttpOnly`, `SameSite` cookies, TLS, session timeout, and session fixation handling. Session fixation protection does not replace cookie protection.
- **Stateless API**: the client typically sends a bearer token on each request; the server validates the token rather than trusting a browser login session. Must validate issuer, audience, signature, expiry, and constraints appropriate to the token format/authentication mechanism. Do not treat a self-decoded JWT as already authenticated.
- **Logout**: clearing the session is effective for server sessions, but does not mean all issued access tokens are revoked. Revocation strategy depends on the token type and identity system.

`SecurityContextHolder` is how running code accesses current security information; it itself is **not** a user database or permanent session store.

### 4.4. Was the Browser-Sent Request Actually Intended by the User? — CSRF

CSRF (Cross-Site Request Forgery) occurs when the browser automatically attaches credentials like a session cookie to a request triggered by another site. If the server relies solely on the cookie to accept data-modifying operations, an attacker can exploit the victim's session.

Spring Security **enables CSRF protection by default** in standard web configurations, which is especially useful for browsers using sessions/cookies. Unsafe requests (`POST`, `PUT`, `PATCH`, `DELETE`...) require a valid CSRF token when within the protected scope. An endpoint with `permitAll()` can still be checked by the CSRF filter.

Only consider disabling or ignoring CSRF **within an analyzed scope** for APIs that do not rely on credentials automatically attached by the browser (for example, APIs that only accept bearer tokens in the `Authorization` header and do not use session cookies). Do not use `csrf.disable()` as a quick fix for 403 missing-token errors in forms/browsers.

### 4.5. Can a Browser from Another Origin Call the API? — CORS

**CORS** is a browser mechanism that checks whether JavaScript from one origin is permitted to access responses from another origin. It is **not** user authorization and does not prevent non-browser clients from sending HTTP requests. Preflight `OPTIONS` requests usually do not carry session cookies; if security blocks preflight before CORS is processed, the UI may report errors even though the endpoint is valid.

Configure the list of origins, methods, headers, and `allowCredentials` according to the actual clients; integrate CORS at the right place in Spring Security/Spring MVC. Do not blindly enable wildcard origins, especially when allowing credentials. CSRF and CORS solve **two different types of risk**.

### 4.6. What Does a Failed Request Return? — 401, 403, and Security Headers

- **401 Unauthorized**: the request lacks or fails authentication credentials; APIs typically return 401 with an authentication challenge if appropriate, while form login may **redirect to the login page**. Do not reduce all unauthenticated cases to a single status code if the application configures redirects.
- **403 Forbidden**: the identity is authenticated but lacks permission, or the request is rejected by another policy (for example, an invalid CSRF token). Therefore, 403 **does not by itself prove** that the issue is a role error.
- **Security headers**: Spring Security can set default protective headers, such as `X-Content-Type-Options: nosniff` and anti-framing policies depending on configuration; **Content-Security-Policy is not automatically added in full for every application**. Define CSP, HSTS, and other headers according to the system's HTTPS/frontend architecture.

`ExceptionTranslationFilter` collaborates with `AuthenticationEntryPoint` and `AccessDeniedHandler` to handle authentication/authorization failure scenarios when exceptions pass through the security mechanism. Do not confuse filter-level security exceptions with MVC business exception handlers.

## 5. Minimal Example: Protecting Three Spring MVC Endpoints

Suppose we create a **Spring Boot 3.x, Java 17+** project using Servlet (web starter) and Spring Security. In the `build.gradle` of a Spring Boot project already configured with plugins/dependency management, include:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create the file `src/main/java/example/security/SecurityDemoApplication.java`. The example intentionally uses only HTTP **GET** to focus on authentication/authorization; CSRF protection remains at its default and no token-handling form is needed yet.

```java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}

@Configuration
class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/profile").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    String publicPage() {
        return "public ok";
    }

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String adminPage() {
        return "admin ok";
    }
}
```

The `WebSecurityConfig` and `DemoController` classes are package-private, so they can reside in the same file as a `public SecurityDemoApplication` class. The file above is compilable Java code when the project has the two Spring Boot starters and an appropriate build plugin. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` encodes new passwords by default using an appropriate algorithm (typically BCrypt via an identifier prefix); do not store plaintext even though the example uses fixed credentials.

Run the project in a practice environment, such as `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). While the application is running on the default port 8080, try:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u learner:demo-pass http://localhost:8080/profile
curl -i -u learner:demo-pass http://localhost:8080/admin
curl -i -u admin:demo-admin http://localhost:8080/admin
```

Expected results for the GET requests (important status and body, ignoring varying headers):

| Request | Status | Content/Explanation |
| --- | --- | --- |
| `GET /public` without credentials | **200** | `public ok`; `permitAll` allows anonymous access |
| `GET /profile` without credentials | **401** | HTTP Basic requires authentication; controller does not run |
| `GET /profile` with `learner` | **200** | `hello learner` |
| `GET /admin` with `learner` | **403** | Authenticated but lacks `ROLE_ADMIN` |
| `GET /admin` with `admin` | **200** | `admin ok` |

Here `hasRole("ADMIN")` matches `ROLE_ADMIN` created by `.roles("ADMIN")`. `anyRequest().denyAll()` demonstrates how to block all routes outside the demo policy; a real application may replace it with `authenticated()` if that is the decided policy. There is only **one** `SecurityFilterChain`, so the chain-ordering problem is not encountered yet.

**Example limitations:** hard-coded usernames/passwords and in-memory storage are only for local learning; do not deploy to the Internet. HTTP Basic must run over HTTPS in real systems. The example does not handle resource ownership, database integration, OAuth2/OIDC, auditing, rate limiting, or cookie-based frontends. When adding POST/PUT/DELETE from a browser, you must design CSRF tokens/cookies appropriately rather than arbitrarily disabling protection.

## 6. From Example to Real Application: Design Questions

Before adding a filter or an annotation, answer these in order:

1. **Which client sends the request?** Server-rendered browser pages, cookie-based SPA, mobile app, or machine-to-machine? The answer affects sessions, Basic, bearer tokens, CSRF, and CORS.
2. **Where does identity live?** Internal database, identity provider, OIDC login, or a resource server verifying access tokens? Who is the issuer, who is the verifier, and who revokes credentials?
3. **What are the resource boundaries?** Only public/user/admin separation, or also owner/organization/tenant? URL rules are only the first line of defense, not a replacement for service/data-level checks.
4. **What is the default for undescribed requests?** Block everything, require login, or allow with clear justification? If there are multiple `SecurityFilterChain`s, which chain matches, in what order, and are there any gaps?
5. **Errors and observability?** Do API 401/403 responses have a stable structure without leaking sensitive information? Do logs/audits distinguish failed logins, insufficient permissions, and CSRF without logging raw passwords/tokens?
6. **How to verify?** Test anonymous users, regular users, admins, cross-resource access, different HTTP methods, CSRF, CORS preflight, and missed routes. Do not test only the authenticated happy path.

A layered example: `GET /orders/123` can require `authenticated()` at the HTTP layer; yet the service still needs to confirm that order 123 belongs to the current user/tenant. Do not assume that having `ROLE_USER` makes reading every order valid.

## 7. Common Mistakes and How to Fix Your Thinking

| Mistake | Why It Is Wrong | How to Handle It |
| --- | --- | --- |
| Treating authentication as authorization | Knowing an identity is not enough to conclude resource access is permitted | Define permissions at the request, service, and object levels |
| Checking permissions only in controllers | Easy to miss new endpoints and reuse unprotected services | Use explicit request configuration; enforce business checks where the data lives |
| Adding `permitAll` and assuming the route skips all protection | Other filters, including CSRF, still run | Understand each filter layer and HTTP method |
| Disabling CSRF because `POST` gets 403 | Can leave cookie-based apps vulnerable to CSRF | Set up CSRF tokens properly; only exclude when proven that no browser-auto-sent credentials are used |
| Thinking CORS is an authorization or anti-CSRF solution | CORS is a browser cross-origin read-control mechanism | Use CORS, CSRF, authentication, and authorization in their proper roles |
| Adding multiple chains with overlapping matchers/order | First matching chain wins; may apply the wrong policy or leave coverage gaps | Check `securityMatcher`, `@Order`, and the fallback chain; test every URL |
| Believing `SecurityContextHolder` crosses all threads automatically | Default context is thread-bound | Use proper propagation mechanisms; avoid holding principals in global state |
| Using Basic over plain HTTP or storing plaintext passwords | Credentials can be exposed | Enforce TLS and use `PasswordEncoder` |
| Returning 403 for all security errors | Obscures differences between unauthenticated, unauthorized, and CSRF failures | Classify and verify actual status codes, handlers, and audits |
| Believing the framework replaces owner/tenant checks | Generic roles do not reflect permissions on specific records | Check ownership/tenant when reading and updating data |

## 8. Self-Check Questions

1. Why are Servlet Filters suitable for protecting requests before Spring MVC, and how does `FilterChainProxy` differ from `SecurityFilterChain`?
2. For a logged-in user viewing another person's order, is adding `.authenticated()` sufficient? Where does the missing check belong?
3. Why can `POST /public` receive 403 even though the endpoint uses `permitAll()`?
4. Given two identical requests where one has no credentials and the other has a user lacking the required role, how do the HTTP results typically differ?
5. When adding a separate chain for `/api/**`, how must you verify matchers, ordering, and the fallback chain so requests are not accidentally left exposed?

**Key takeaway:** In a Servlet application, Spring Security places an authentication, authorization, and HTTP protection system on the Servlet Filter flow. The framework provides the mechanisms; correctness depends on choosing the right policies for your application's clients, resources, login state, and request types.
