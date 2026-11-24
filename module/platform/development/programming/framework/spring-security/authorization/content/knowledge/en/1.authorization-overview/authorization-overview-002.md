# Distinguishing Identity Authentication from Authorization Decisions in Spring Security

> **Scope:** Spring Security for Servlet/Spring MVC web applications. The focus is on recognizing two distinct security steps—**authentication** and **authorization**—and seeing how they work together during a request.

## 1. Two Different Questions

- **Authentication — "Who are you?"**: The system verifies proof of identity (e.g., username/password, login session, verified access token). When successful, it obtains information about the principal and a trusted authentication state.
- **Authorization — "Is that subject allowed to perform this action on this resource?"**: The system applies an access policy to the known user or anonymous user, together with the **action**, **resource**, and potentially **context**. The result is allow or deny.

For example: Alice logs in successfully but only has the `USER` role. Alice's request `GET /admin/panel` is denied by the `hasRole("ADMIN")` rule. **Successful login does not mean having every permission.** Conversely, `GET /public/ping` can be accessed without logging in because of the `permitAll()` policy.

| Perspective | Authentication | Authorization |
| --- | --- | --- |
| Question | Who is sending the request, and is the proof of identity valid? | Is that person allowed to do this with this resource? |
| Key data | Credentials/token/session and the corresponding verification mechanism | `Authentication`, `GrantedAuthority`, HTTP path/method, Java method, resource owner, business rules |
| Outcome | Identity is authenticated and placed in the security context, or fails/unauthenticated | Allow/deny decision; may require authentication first |
| Failure scenarios | Wrong password, expired token, no credentials provided for a protected resource | Valid identity but missing role/authority, or not the resource owner |
| Common Spring Security components | `AuthenticationManager`, `AuthenticationProvider`, authentication filters, `SecurityContextHolder` | `AuthorizationManager`, `AuthorizationFilter`, `authorizeHttpRequests`, `@PreAuthorize` |
| Practical meaning | "I know you are Alice." | "Is Alice allowed to view the admin report?" |

**Additional distinction:** "Authenticated?" is different from "Authorized?". `authenticated()` in HTTP configuration only requires an appropriate authentication state; `hasRole(...)` / `hasAuthority(...)` / ownership rules also check access conditions.

## 2. How Does Spring Security Store Identity and Make Decisions?

On the **authentication** side:

1. A mechanism such as HTTP Basic, form login, or Bearer token handles login data. The specific mechanism determines how credentials/tokens are verified; not every request enters a password.
2. For a login flow based on `AuthenticationManager`, the manager delegates the request to a suitable `AuthenticationProvider`. When verification succeeds, the system has an `Authentication` representing the authenticated principal.
3. `SecurityContext` holds the `Authentication` for the current request; Servlet code typically accesses it via `SecurityContextHolder`. `Authentication#getName()` returns the principal name, while `getAuthorities()` returns the collection of assigned `GrantedAuthority` instances.

On the **authorization** side:

1. HTTP rules in `authorizeHttpRequests` match the request and select the policy in **declaration order**; typically only the first matching rule is used.
2. `AuthorizationFilter` uses an `AuthorizationManager` to evaluate the request, retrieving `Authentication` from the security context when needed. A `permitAll()` rule can allow access without reading the identity.
3. After passing the HTTP check, a business method may still have an independent permission check via `@PreAuthorize` if the application enables method security.

~~~text
Client sends GET /admin/panel
  -> SecurityFilterChain (Servlet)
     -> Authentication mechanism (if needed; e.g., Basic)
        -> SecurityContext / Authentication {principal, authorities}
     -> AuthorizationFilter + HTTP policy
        -> RULE SATISFIED: proceed to controller/service
        -> NOT SATISFIED: deny
     -> Method security (if @PreAuthorize is on a Spring-managed bean)
        -> SATISFIED: execute business logic
        -> NOT SATISFIED: deny
~~~

The diagram above is a **conceptual flow**, not an exhaustive list of every filter. Exception-handling components also participate in the chain. In an application using Bearer JWTs, **verifying the token signature, expiration, and trust conditions** belongs to authentication; **checking scopes, roles, permissions, or ownership** for the endpoint belongs to authorization.

### Principal, role, and authority

- **Principal**: the identified subject, e.g., `alice`. It answers *who*.
- **Authority**: a permission/permission label assigned by the system to `Authentication`, e.g., `ROLE_ADMIN`, `invoice:read`. It is input data for policies, **not an automatic grant everywhere**.
- **Role**: a way of organizing authorities. With the default configuration, `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority; `hasAuthority("ROLE_ADMIN")` matches that string directly. `hasAuthority("invoice:read")` checks the exact `invoice:read` authority.
- **Per-resource rules**: even two users sharing the `USER` role are not automatically allowed to read each other's invoices; you may need to check `invoice.ownerId == authentication.name` in the service layer or via a dedicated `AuthorizationManager`.

Note: Spring Security may place an `AnonymousAuthenticationToken` in the `SecurityContext` when a user is not logged in. Therefore, **merely checking `authentication != null` or relying on `Authentication#isAuthenticated()` alone is not enough to conclude that this is a genuinely logged-in user**. Use the framework's `authenticated()` rule or `AuthenticationTrustResolver` when you need to distinguish anonymous users.

## 3. Java 17+ Example: One Application, Two Check Layers

The example below runs in a **Spring Boot project using Java 17+** with the **Spring Web** and **Spring Security** dependencies (for instance, a Maven project generated with Spring Initializr). This is complete application code for a single Java file; Spring Boot and its starters provide the required libraries, so **do not use `javac` alone to compile this file without setting up the classpath**.

Create or replace the file `src/main/java/com/example/demo/SecurityDemoApplication.java`; make sure the package matches your project.

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/profile/me", "/reports/summary").authenticated()
                .requestMatchers("/admin/panel").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }

    @RestController
    static class ApiController {
        private final ReportService reportService;

        ApiController(ReportService reportService) {
            this.reportService = reportService;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/profile/me")
        String me(Authentication authentication) {
            return authentication.getName();
        }

        @GetMapping("/admin/panel")
        String panel() {
            return "admin data";
        }

        @GetMapping("/reports/summary")
        String report() {
            return reportService.summary();
        }
    }

    @Service
    static class ReportService {
        @PreAuthorize("hasRole('ADMIN')")
        public String summary() {
            return "quarterly report";
        }
    }
}
~~~

Run with Maven Wrapper in the project directory:

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

Once the application is running on the default port 8080, try the following GET requests (these passwords are **for demo purposes only**; do not use them as-is in production):

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/profile/me
curl -i -u alice:demo123 http://localhost:8080/profile/me
curl -i -u alice:demo123 http://localhost:8080/admin/panel
curl -i -u bob:demo456 http://localhost:8080/admin/panel
curl -i -u alice:demo123 http://localhost:8080/reports/summary
curl -i -u bob:demo456 http://localhost:8080/reports/summary
~~~

| Request | Expected Outcome | Reason |
| --- | --- | --- |
| `/public/ping`, no credentials | `200`, body `pong` | `permitAll()` policy |
| `/profile/me`, no credentials | `401 Unauthorized` | Endpoint requires authentication; HTTP Basic requests credentials |
| `/profile/me`, Alice | `200`, body `alice` | Alice is authenticated; no specific role required |
| `/admin/panel`, Alice | `403 Forbidden` | Alice authenticates successfully but lacks `ROLE_ADMIN` |
| `/admin/panel`, Bob | `200`, body `admin data` | Bob has `ROLE_ADMIN` |
| `/reports/summary`, Alice | `403 Forbidden` | Passes HTTP `authenticated()` rule, but denied by `@PreAuthorize` on the service |
| `/reports/summary`, Bob | `200`, body `quarterly report` | Passes both HTTP and method security layers |

**What to observe:** `/reports/summary` only requires login at the HTTP level, yet the service still enforces the admin role. This clearly demonstrates that "authentication succeeded" is not enough to execute a business method. `@EnableMethodSecurity` activates checks such as `@PreAuthorize`; the Spring Boot Security starter does not automatically enable method security just by having the dependency. The call from controller -> `ReportService` bean goes through a Spring proxy; if a method within the same bean calls a `@PreAuthorize`-annotated method via `this`, it can bypass AOP checks under the standard proxy mechanism.

### HTTP 401, 403, and login redirects

In the example using HTTP Basic, when credentials are missing for a resource that requires authentication, the entry point returns `401 Unauthorized`; an authenticated user lacking permission typically receives `403 Forbidden`.

Spring Security uses `ExceptionTranslationFilter` to convert security exceptions into the appropriate HTTP flow:

- An `AuthenticationException` or a request denied in an anonymous context usually triggers `AuthenticationEntryPoint` (HTTP Basic typically returns 401; form login may return a **302 redirect** to the login page).
- An `AccessDeniedException` from an authenticated user usually goes to `AccessDeniedHandler` (the default is typically 403).

Therefore, **do not assume "every authentication error is always 401" or "every authorization denial is always 403"** while ignoring the login mechanism, anonymous handling, and entry point configuration. In API applications, define a clear error response contract.

## 4. Applying This to Real-World Scenarios

**Invoice API:**

- Authentication: verify the access token and identify `alice`; map the valid granted authorities.
- Endpoint-level authorization: only callers with `invoice:read` may call `GET /invoices/{id}`.
- Object-level authorization: load the invoice to be read and check `invoice.ownerId == alice.id`, or an explicitly designed administrative permission.
- Conclusion: Alice having general permission to read invoices **still does not necessarily mean she can read Bob's invoice**. Checking roles/scopes at the URL level is insufficient for specific resources.

**Sound policy placement:** use `authorizeHttpRequests` to protect HTTP routes, use `@PreAuthorize` or an `AuthorizationManager`/policy service for decisions close to business logic, and apply **deny by default** for endpoints without rules. Never treat hiding buttons in the frontend or hard-to-guess paths as an authorization measure.

## 5. Common Misconceptions

1. **"A valid token grants access to every API."** False: a valid token establishes a trusted identity/context; the API still checks scope, role, action, and resource. Authorities from a token are only trustworthy after the token has been properly verified.
2. **"`authenticated()` is an admin check."** False: it is an authentication requirement; admin access needs `hasRole("ADMIN")` or an equivalent policy.
3. **"`hasRole("ADMIN")` is the same as `hasAuthority("ADMIN")`."** Not true with the default role prefix: `hasRole("ADMIN")` checks `ROLE_ADMIN`, whereas `hasAuthority("ADMIN")` checks the string `ADMIN`. The prefix is customizable.
4. **"Having an `Authentication` means the user is logged in."** False for anonymous tokens; use Spring Security's anonymous-detection mechanisms.
5. **"Blocking the URL is enough."** Not necessarily: a service called from elsewhere (jobs, other REST endpoints, message consumers) may need method/domain policies. When using `@PreAuthorize` with AOP, avoid self-invocation within the same bean if you expect the proxy to intercept it.
6. **"`permitAll()` means bypassing Spring Security."** No: the request still goes through the security filter chain; `permitAll()` is simply the authorization decision for that route, unlike ignoring all filters.
7. **"Rule order doesn't matter."** `authorizeHttpRequests` evaluates in order; put `anyRequest()` last and order specific rules before broad rules.
8. **"Basic Authentication automatically encrypts passwords on the wire."** No: Basic encodes with Base64, not cryptographic encryption; real systems must use HTTPS. Hardcoded accounts/passwords in examples are for learning purposes only.

## 6. Self-Check Questions

1. Alice is logged in with `ROLE_USER` but does not have `ROLE_ADMIN`. Should `hasRole("ADMIN")` allow or deny? **Deny**; authentication succeeded, but authorization failed.
2. Endpoint `/health` has `permitAll()`; can an unauthenticated user be allowed? **Yes**, provided no other policy blocks the request.
3. Bob has `invoice:read` but requests to read Alice's invoice. What else is needed? **An authorization check on the object itself**, such as ownership or access relationship.
4. Why can `/reports/summary` in the example return 403 even though HTTP declares `authenticated()`? Because **the service's `@PreAuthorize` continues to evaluate `ROLE_ADMIN`**.
5. Can you tell immediately which APIs a user can access just by looking at `Authentication#getAuthorities()`? **No**; the decision also depends on endpoint policies, method policies, and resource data.

**Remember:** *Authentication determines "who", while authorization decides "what can be done with what, under what circumstances".* Spring Security uses identity and authorities as **inputs** to policies; a successful authentication result does not replace an authorization decision.

## Official Documentation

- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Anonymous Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
