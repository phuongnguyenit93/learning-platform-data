# Authentication, Authorization, and Exploit Protection: The Three Core Pillars of Spring Security

In a Spring application using Servlet/Spring MVC, Spring Security provides mechanisms to **identify who is sending a request**, **decide what that entity is allowed to do**, and **mitigate common web application attacks**. These are three related functional groups with distinct purposes: **authentication**, **authorization**, and **exploit protection**.

## 1. The Big Picture: Three Different Questions

| Functional Group | Core Question | Example | Expected Outcome |
| --- | --- | --- | --- |
| Authentication | "Who are you? Do you have trustworthy proof?" | Verify username/password, HTTP Basic, bearer token | Establish an authenticated identity along with its granted authorities |
| Authorization | "Is this identity allowed to perform this action?" | Only ADMIN can call `/api/admin/**`; users only view their own data | Allow or deny access to a resource/feature |
| Exploit protection | "Could the request or response be abused in a known way?" | Verify CSRF token, add security headers, support session protection | Reduce attack risks even when login and authorization rules exist |

Example: Alice logs in validly, but she is not an administrator. The system **successfully authenticates** Alice, then **denies authorization** for the administrative operation. If Alice is logged in via a cookie and an unfamiliar website tries to submit a money transfer command on Alice's behalf, **CSRF protection** must also validate the legitimacy of the state-changing request. These three tasks do not replace one another.

Spring Security primarily applies policies inside the Servlet application's **`SecurityFilterChain`**. A request passes through matching security filters before reaching a controller. The filters may handle authentication, security context, CSRF, and access decisions; the exact order depends on configuration. Having a valid username in a request does not mean the request is allowed to bypass every check layer.

## 2. Authentication: Knowing the Caller's Identity

### 2.1. What Does Authentication Verify?

Authentication is the process of verifying proof of identity: a password, certificate, token, or equivalent mechanism for the system. If valid, Spring Security represents the identity with an **`Authentication`** object. This object typically contains:

- **`principal`**: the authenticated user or subject;
- **`credentials`**: information used to prove identity, restricted/cleared when appropriate;
- **`authorities`**: a collection of `GrantedAuthority`, such as `ROLE_ADMIN` or permission `invoice:read`;
- **`isAuthenticated()`**: the authentication state of the object.

Common components:

- `AuthenticationManager` is the interface coordinating authentication; a common implementation is `ProviderManager`.
- One or more `AuthenticationProvider` instances know how to handle a specific authentication mechanism, such as username/password.
- `SecurityContext` stores the current `Authentication`; `SecurityContextHolder` is the access point to that context in a standard Servlet processing thread.
- `AuthenticationEntryPoint` handles situations where the user needs to provide credentials, such as returning HTTP 401 with `WWW-Authenticate` or redirecting to a login page.

Conceptual processing flow:

```text
Request + credentials
        |
        v
Security Filter -> AuthenticationManager -> AuthenticationProvider
                                                |
                                    authentication succeeds/fails
                                                |
                   success -> Authentication -> SecurityContext
                                                |
                                      continue to permission checks
```

This is a logical model, not a fixed ordering diagram of all filters. With session login, the authentication context can be restored from the session; with a bearer token, the system typically validates the token per request. How the context is stored or rebuilt depends on the mechanism and configuration.

### 2.2. Examples and Common Pitfalls

- **A successful login** proves identity at the time of verification; it does not guarantee access to `/admin`.
- **An unauthenticated user** and **an authenticated user lacking permission** are two different cases.
- Passwords should be stored as a **proper hash**, using `PasswordEncoder`; do not store plaintext or compare hashes manually.
- When using HTTP Basic, login credentials are sent in the `Authorization` header on every request. You must use HTTPS in production; Base64 in HTTP Basic is not secure encryption.
- A valid bearer token also does not mean the caller is allowed to invoke every API: the application must still check authorities, scopes, and resource boundaries.

## 3. Authorization: Deciding What Is Allowed

Once an identity is established, the system decides whether to allow a specific action based on policy and context. Spring Security supports multiple levels of checks:

1. **By HTTP request**: path, HTTP method, and rules in `authorizeHttpRequests`, such as public GET requests, admin paths restricted to ADMIN, and the rest requiring login.
2. **By method**: `@PreAuthorize`, `@PostAuthorize`, or method security mechanisms when enabled via `@EnableMethodSecurity`. Useful when a business service is also invoked from multiple entry points.
3. **By object/resource**: checking whether the accessing user has permission for that specific order, profile, or tenant. Simply having the "USER" role does not prove a user owns a particular order.

### 3.1. Role, Authority, and Resource Scope

`GrantedAuthority` is a permission string granted to a user. A **role** is typically represented as an authority prefixed with `ROLE_`. In the default configuration:

- `hasRole("ADMIN")` checks the authority `ROLE_ADMIN`;
- `hasAuthority("invoice:read")` checks the exact string `invoice:read`;
- `User.withUsername(...).roles("ADMIN")` creates the authority `ROLE_ADMIN`.

Do not confuse **role** with every kind of permission. Someone with `ROLE_USER` still must not be allowed to modify another user's data; ownership/tenant checks usually require additional business logic.

Request-matching rules are evaluated in the order declared. Therefore, more specific rules must appear before broader rules:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/articles").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

`permitAll()` means the endpoint is public with respect to **access permissions**; it does not mean the request bypasses all security filters. For instance, a public POST may still have to pass CSRF if the application enables that mechanism. For sensitive systems, design according to the **principle of least privilege** and deny unannounced resources by default; the final rule can be `denyAll()` if policy requires explicitly listing every permitted endpoint.

### 3.2. HTTP 401, 403, and Login Redirects

- **401 Unauthorized**: typically a request missing or carrying invalid authentication credentials, especially with HTTP Basic/APIs.
- **403 Forbidden**: the request lacks sufficient access permission or was blocked by a protection layer such as CSRF.
- **302 Redirect** to a login page: may appear when an application uses form login instead of returning 401 directly.

Do not conclude "every 403 is due to a missing role": a missing/invalid CSRF token also frequently produces 403. Conversely, you cannot rely on the HTTP status code alone to deduce the entire cause; you must inspect the security configuration and relevant logs.

## 4. Exploit Protection: Hardening Requests, Responses, and Sessions

Authentication and authorization are essential, but not sufficient. Browsers attach cookies automatically, malicious code can attempt to force users into sending requests, applications can respond without defensive headers, and many vulnerabilities can exist in business code.

### 4.1. CSRF: A Classic Example with Cookie Authentication

**Cross-Site Request Forgery (CSRF)** occurs when a malicious page causes a logged-in victim's browser to send a state-changing request to a target application. The browser may automatically send the session cookie, so a server relying solely on the cookie mistakes the request for the victim's intent.

Example: a victim is logged into `bank.example`; a malicious page tricks the browser into sending a POST to transfer money. If the application uses session cookies without verifying request legitimacy, a successful login and a rule saying "logged-in users can transfer money" are not enough to prevent forgery.

Spring Security enables **CSRF protection** by default in Servlet configuration. For unsafe HTTP methods such as POST/PUT/PATCH/DELETE, the request must supply a valid CSRF token under the active mechanism. GET/HEAD/OPTIONS/TRACE normally do not require a CSRF token; therefore the application must adhere to the principle that **GET does not mutate state**.

Distinguish carefully:

- **Cookie/session login**: CSRF is a major threat because the browser can automatically send authentication credentials.
- **Truly stateless APIs** that only accept bearer tokens from the client-controlled `Authorization` header and do not use browser-auto-attached credentials: you can evaluate not applying CSRF to those endpoints. This decision must be based on how the client actually authenticates, not on the word "REST".
- **CORS** decides whether JavaScript on another origin is allowed to read/call cross-origin resources under browser policy. CORS is not an identity check, does not replace authorization, and does not solve CSRF on its own.

Do not disable CSRF application-wide just to stop test POST commands from returning 403. First determine the authentication mechanism, how CSRF tokens are issued, and which endpoints need protection.

### 4.2. Security Headers and Session Protection

Spring Security can add HTTP response headers to strengthen browser defenses, such as:

- `X-Content-Type-Options: nosniff`: reduces unwanted browser MIME-type sniffing;
- `Strict-Transport-Security` (HSTS) when served over HTTPS and configured appropriately: encourages the browser to use HTTPS only on subsequent visits;
- cache directives and other security headers depending on configuration/version.

Depending on requirements, the application also needs a **Content Security Policy**, proper `Secure` / `HttpOnly` / `SameSite` cookie attributes, HTTPS, and secure session management. Do not assume every defensive header is automatically enabled with values appropriate for every system.

Spring Security also includes mechanisms to support session management, logout handling, and defenses against certain session-related risks. However, it **does not automatically replace** input validation, output encoding against XSS, parameterized queries against SQL injection, rate limiting, secret management, or authorization checks on business objects.

## 5. Runnable Example in a Spring Boot 3 / Java 17+ Application

The example illustrates all three functional groups in a **Spring MVC (Servlet)** application: a public endpoint, an endpoint requiring authentication, an endpoint requiring the ADMIN role, and a POST subject to CSRF. You need a Spring Boot 3 project using Java 17 or higher, configured with the Spring Boot Gradle plugin, with at least two dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create `src/main/java/example/securitydemo/SecurityDemoApplication.java`:

```java
package example.securitydemo;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class DemoController {
    @GetMapping("/public/articles")
    Map<String, String> publicArticles() {
        return Map.of("message", "public");
    }

    @GetMapping("/account")
    Map<String, String> account(Principal principal) {
        return Map.of("user", principal.getName());
    }

    @GetMapping("/admin/health")
    Map<String, String> adminHealth() {
        return Map.of("status", "ok");
    }

    @PostMapping("/account/settings")
    Map<String, String> updateSettings(Principal principal) {
        return Map.of("updatedBy", principal.getName());
    }
}
```

Create `src/main/java/example/securitydemo/SecurityConfig.java`:

```java
package example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/articles").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails member = User.withUsername("member")
            .password(encoder.encode("demo-member-secret"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-secret"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(member, admin);
    }
}
```

Configuration explanation:

1. `SecurityFilterChain` declares the security policy for requests in the application.
2. `GET /api/public/articles` has `permitAll()`; `/api/admin/**` requires `ROLE_ADMIN`; all remaining requests require authentication.
3. `httpBasic()` enables HTTP Basic authentication, allowing quick testing via `curl -u`; `InMemoryUserDetailsManager` provides two demo users; passwords are hashed with BCrypt.
4. `csrf(Customizer.withDefaults())` retains default CSRF protection instead of disabling it for POST.
5. `@EnableMethodSecurity` allows adding rules on services with `@PreAuthorize` when the application needs method-level authorization. This example does not yet use that annotation on the controller.

The two accounts and passwords above **are only for local learning**. Real-world applications must use a properly managed identity/secret store, restrict credentials, and transmit HTTP Basic only over TLS.

Run in the configured Boot project:

```bash
./gradlew bootRun
```

On Windows you can use `gradlew.bat bootRun`. Verify the following behaviors with the server running at `localhost:8080`:

```bash
# Public GET: 200, body {"message":"public"}
curl -i http://localhost:8080/api/public/articles

# No credentials: 401 (HTTP Basic challenge)
curl -i http://localhost:8080/api/account

# Authenticated member: 200, body {"user":"member"}
curl -i -u member:demo-member-secret http://localhost:8080/api/account

# member lacks ROLE_ADMIN: 403
curl -i -u member:demo-member-secret http://localhost:8080/api/admin/health

# admin has ROLE_ADMIN: 200, body {"status":"ok"}
curl -i -u admin:demo-admin-secret http://localhost:8080/api/admin/health

# POST without CSRF token: 403, even with valid Basic credentials
curl -i -X POST -u member:demo-member-secret http://localhost:8080/api/account/settings
```

The JSON bodies above are the expected output from the controllers; status codes may differ if you change security configuration, add middleware, or configure a different authentication mechanism. For the POST endpoint, to allow a valid request in a CSRF-enabled model, the client must obtain and send the CSRF token according to the rules of the active `CsrfTokenRepository`/`CsrfTokenRequestHandler`. You do not need to remove the CSRF layer just to demonstrate that authentication or authorization works.

### 5.1. Adding Permission Checks in Business Logic

URL rules are only one layer of defense. Suppose a user calls `GET /api/orders/123` and already has `ROLE_USER`; the application must still confirm order 123 belongs to that user (or that they have delegated permission). This check typically lives in the service, possibly combining `@PreAuthorize` with ownership/tenant verification.

Example of a standalone method security rule, **illustrating the annotation only**:

```java
@PreAuthorize("hasAuthority('invoice:approve')")
public void approveInvoice(long invoiceId) {
    invoiceService.approveIfAllowed(invoiceId);
}
```

The snippet above assumes `invoiceService` is already defined and already checks permission on the specific invoice; this is not a standalone program. The authority `invoice:approve` must actually be present in the subject's `Authentication.authorities`. Do not merely hide a button in the UI and treat that as authorization.

## 6. Analyzing Requests Across the Three Layers

| Scenario | Authentication | Authorization | Exploit Protection | Result in Example |
| --- | --- | --- | --- | --- |
| Guest GET `/api/public/articles` | Not required | `permitAll()` | Applicable filter/header layers still run | 200 |
| Guest GET `/api/account` | No credentials | Endpoint needs an authenticated user | CSRF not involved because GET | 401 with HTTP Basic |
| `member` GET `/api/account` | Succeeded | `authenticated()` accepts | Applicable protections applied | 200 |
| `member` GET `/api/admin/health` | Succeeded | Lacks `ROLE_ADMIN` | CSRF not involved because GET | 403 |
| `admin` GET `/api/admin/health` | Succeeded | Has `ROLE_ADMIN` | Applicable protections applied | 200 |
| `member` POST `/api/account/settings` without CSRF token | Valid credentials | Endpoint requires login | **CSRF rejects the request** | 403 |

The table helps distinguish **"could not identify who it is"**, **"identified, but lacks permission"**, and **"request failed an exploit protection check"**. Filters may reject a request before other layers make a final decision; not every request passes through all three functional groups in a strict linear order.

## 7. Common Mistakes and How to Avoid Them

1. **Treating authentication as authorization.** A successful login does not imply administrative rights, access to others' data, or permission for every action. Explicit policies are needed at the request and business service layers.
2. **Confusing `hasRole` with `hasAuthority`.** `hasRole("ADMIN")` checks `ROLE_ADMIN` by default, whereas `hasAuthority("ADMIN")` checks the exact string `ADMIN`. Choose a consistent convention so endpoints are not accidentally exposed or locked out.
3. **Declaring overly broad rules before specific rules.** Matchers are evaluated in order; place specific cases before `anyRequest()` and test both permitted and denied access.
4. **Blanket-disabling CSRF because POST returns 403.** Analyze which clients automatically send cookies/credentials, which requests mutate state, and how CSRF tokens are issued. For apps using sessions/cookies, keeping CSRF enabled is the safe default.
5. **Assuming CORS or HTTPS replaces authorization.** HTTPS protects data in transit; CORS is a browser cross-origin access policy; neither decides whether an account may modify data.
6. **Assuming Spring Security blocks all attacks.** You also need input validation, output encoding, parameterized queries, data access controls, monitoring, rate limiting, and infrastructure configuration. Security headers reduce risk but do not automatically patch bugs in code.
7. **Testing only the happy path.** At minimum, test anonymous access, an account with the right role, an account lacking permission, invalid credentials, a POST request missing a CSRF token, and accessing another user's resource.

## 8. Key Takeaways and Self-Check

- **Authentication = verify identity** and build/contextualize `Authentication`.
- **Authorization = make access decisions** via URL rules, method rules, and resource-level permissions.
- **Exploit protection = reduce risks from how requests/responses/sessions can be abused**, notably CSRF and security headers.
- For APIs returning HTTP Basic, **401** is usually an authentication issue; **403** may be due to missing permissions or CSRF. With form login, the app may redirect.
- `permitAll()` does not mean disabling all filters; a request can be public regarding access permissions yet still subject to other protective mechanisms.

Self-check questions:

1. Someone with `ROLE_USER` logs in successfully and then calls `/api/admin/health`. Which functional group explains returning 403?
2. Why can a POST with a valid session cookie still be rejected if the CSRF token is missing?
3. Why does `hasRole("ADMIN")` differ from `hasAuthority("ADMIN")` when using the default role prefix?
4. If two users both have `ROLE_USER`, what ensures user A cannot view user B's orders?
5. Why can't you rely solely on CORS, HTTPS, or hiding UI buttons to replace backend permission checks?

Suggested answers: (1) authorization; (2) an auto-attached cookie does not prove user intent, so CSRF needs proof of a legitimate request; (3) `hasRole` automatically prepends `ROLE_` by default convention; (4) ownership/tenant checks at the business layer; (5) those measures solve different problems and do not govern a subject's permission for an action/resource.

### Official References

- [Spring Security – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Cross-Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
