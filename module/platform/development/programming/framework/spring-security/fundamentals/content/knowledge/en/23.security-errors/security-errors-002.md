# 401 Unauthorized, 403 Forbidden, and Redirecting to the Login Page

## 1. Identifying the Three Outcomes Correctly

When accessing a protected resource, you must distinguish **authentication**—determining who is sending the request—from **authorization**—determining whether the identified user is allowed to perform the action. In Servlet-based Spring Security applications, the three outcomes below commonly appear:

| HTTP Outcome | Meaning for the Request | Typical Scenario |
| --- | --- | --- |
| **401 Unauthorized** | The request requires valid authentication credentials or the credentials sent were not accepted. The standard name contains "Unauthorized", but the issue is primarily **authentication**. | Calling a REST API without sending credentials or sending an invalid Basic/Bearer token. |
| **403 Forbidden** | The server understands the request but refuses to fulfill it; very common when an authenticated identity lacks the required permissions. | A user with `ROLE_USER` calls an endpoint requiring `ROLE_ADMIN`; a POST request missing a valid CSRF token can also return 403. |
| **302 Found** with `Location: /login` | The server asks the browser to navigate to the login page. This is an **HTTP redirect**, not a 401/403 status code. | An unauthenticated user opens a protected web page when the application uses form login. |

**There is no rule that "unauthenticated always returns 401, authenticated always returns 403".** How authentication starts depends on the `AuthenticationEntryPoint` configured for the request. The same unauthenticated request without a login session might be redirected to a login page on the web UI, yet receive 401 on a REST API. Conversely, certain checks such as CSRF can return 403 even though the issue does not stem from a missing role.

For example, for the same `/admin` resource:

- On a **website using form login**: unauthenticated → `302 Location: /login`; logged in with an account lacking an admin role → usually `403`; with an admin role → processed successfully.
- On an **API using HTTP Basic**: no credentials sent → `401` with `WWW-Authenticate` header; authenticated but lacking the role → `403`; authorized → processed successfully.

## 2. Who Decides Whether to Return 401, 403, or a Redirect?

In Servlet Spring Security, requests pass through `FilterChainProxy` and a matching `SecurityFilterChain`. Authorization filters, such as `AuthorizationFilter`, can deny access; `ExceptionTranslationFilter` translates security exceptions thrown downstream of it into appropriate HTTP behavior.

High-level processing flow:

1. **Request arrives** → the matching filter chain is selected.
2. **Authentication**: mechanisms such as form login, HTTP Basic, or Bearer tokens identify the user and establish security information when valid.
3. **Authorization**: rules such as `permitAll()`, `authenticated()`, `hasRole(...)`, `hasAuthority(...)`, etc. decide whether access is allowed.
4. If an `AuthenticationException` occurs, or an `AccessDeniedException` requires initiating authentication for an unauthenticated user, `ExceptionTranslationFilter` invokes **`AuthenticationEntryPoint`**. The entry point can return 401/a challenge or redirect to the login page.
5. If appropriately identified but lacking permissions and an `AccessDeniedException` occurs, the filter invokes **`AccessDeniedHandler`**, which by default usually returns 403.

`ExceptionTranslationFilter` **does not perform authentication or authorization itself**; it connects security exceptions to HTTP responses. Errors arising directly inside the login filter or CSRF filter may be handled by that filter's own mechanism, so do not assume every error travels through the exact same exception-throwing path.

`AuthenticationEntryPoint` and `AccessDeniedHandler` do two different jobs:

| Component | Answers the question | Example behavior |
| --- | --- | --- |
| `AuthenticationEntryPoint` | "How should authentication be started/continued?" | `LoginUrlAuthenticationEntryPoint` returns 302 to `/login`; `BasicAuthenticationEntryPoint` returns 401 and an HTTP Basic challenge. |
| `AccessDeniedHandler` | "How should the current access denial be handled?" | `AccessDeniedHandlerImpl` sends 403; can be configured with an error page or JSON depending on the application. |

The `anonymous` state in Spring Security is a mechanism representing an unauthenticated user; it **does not mean** the user is authenticated just because an `Authentication` object may exist in `SecurityContext`. When `AccessDeniedException` occurs for an anonymous user, the flow usually initiates authentication first rather than assuming a missing role and returning 403.

## 3. Why Does a Website Redirect to the Login Page?

With `formLogin(Customizer.withDefaults())`, Spring Security provides a default login page at `GET /login` and processes login submissions at `POST /login`. When an unauthenticated user requests a path requiring authentication:

1. The browser calls `GET /profile`.
2. The `authenticated()` rule is not satisfied; `LoginUrlAuthenticationEntryPoint` sends a `302` response with `Location` pointing to `/login`.
3. The browser automatically follows the redirect, calls `GET /login`, and receives the login page HTML (usually `200 OK`).
4. The user submits the `POST /login` form with `username`, `password`, and a valid CSRF token.
5. If login succeeds, Spring Security usually redirects back to the request saved in `RequestCache`, or to a default URL if no request was saved. If login fails, the default configuration redirects to `/login?error`.

Therefore, **the login page returning 200 does not mean the initial `/profile` request succeeded**. Open DevTools' Network tab and inspect the entire `302 → /login → 200` sequence. HTTP tools usually let you choose whether to follow redirects automatically; `curl -i` shows the first 302 response by default, whereas `curl -L` follows redirects.

When setting `formLogin(form -> form.loginPage("/sign-in"))`, the application itself must provide `GET /sign-in` and ensure the login URL and assets are permitted. If you forget `permitAll()` for a custom login page, login requests can enter a redirect loop. With HTML forms using sessions/cookies, keep CSRF protection enabled and submit a valid CSRF token.

## 4. Hands-on: An Application Distinguishing Web and API

This example uses **Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet)**. Create a Gradle project with Spring Initializr including the `Spring Web` and `Spring Security` dependencies, then place the file `src/main/java/demo/SecurityStatusDemoApplication.java` as follows. Two `SecurityFilterChain` beans are clearly separated so `/api/**` uses HTTP Basic while web pages use form login. The code is a complete Spring Boot program within a project having those dependencies; it cannot be compiled with plain `javac` alone without Spring libraries.

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableWebSecurity
public class SecurityStatusDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityStatusDemoApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    public static class Endpoints {
        @GetMapping("/public")
        public String publicWeb() {
            return "public-web";
        }

        @GetMapping("/profile")
        public String profile() {
            return "profile";
        }

        @GetMapping("/admin")
        public String adminWeb() {
            return "admin-web";
        }

        @GetMapping("/api/public")
        public String publicApi() {
            return "public-api";
        }

        @GetMapping("/api/admin")
        public String adminApi() {
            return "admin-api";
        }
    }
}
```

**Explanation of key points:**

- `@Order(1)` ensures the API chain is evaluated first. `securityMatcher("/api/**")` defines the **scope of the entire chain**; `requestMatchers(...)` inside only define **access rules** after the chain has been selected. The web chain then handles the remaining URLs.
- `httpBasic(...)` uses an HTTP Basic challenge to request credentials; in this example, the API does not enable form login. `SessionCreationPolicy.STATELESS` and `NullRequestCache` avoid storing sessions/previous requests for the example's API flow.
- `formLogin(...)` enables the default login page for the web flow. The program does **not** disable CSRF globally.
- `hasRole("ADMIN")` requires the `ROLE_ADMIN` authority; `roles("ADMIN")` creates that exact authority. Using `hasAuthority("ADMIN")` is a different check and does not automatically prepend `ROLE_`.
- The in-memory accounts `alice/demo-pass` and `admin/admin-pass` are for local testing only. Passwords are encoded at startup via `DelegatingPasswordEncoder`; real applications must manage accounts and secrets securely, and transmit HTTP Basic only over HTTPS.

Run the project using the Gradle Wrapper:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

Test the API from another terminal; the results on the right are **HTTP status codes and relevant body/header parts**, not the full `curl` output:

```bash
curl -i http://localhost:8080/api/public
# 200 OK; body: public-api

curl -i http://localhost:8080/api/admin
# 401 Unauthorized; WWW-Authenticate: Basic ...

curl -i -u alice:demo-pass http://localhost:8080/api/admin
# 403 Forbidden

curl -i -u admin:admin-pass http://localhost:8080/api/admin
# 200 OK; body: admin-api

curl -i http://localhost:8080/profile
# 302 Found; Location points to /login
```

Do not assume all headers, dates, cookies, or error page contents are identical across versions and environments; what needs verification is the **status**, `Location`/`WWW-Authenticate` where applicable, and the endpoint body on successful access.

Then open a fresh browser or incognito window:

1. Visit `http://localhost:8080/profile` while unauthenticated → redirected to the login page.
2. Log in as `alice / demo-pass` → taken to the requested page (usually `/profile`), seeing `profile`.
3. Open `/admin` in the same session → `403` because `alice` only has `ROLE_USER`.
4. Log out or use a new browser session, log in as `admin / admin-pass` → `/admin` returns `admin-web`.

Table of expected results:

| Request | Context | Main outcome |
| --- | --- | --- |
| `GET /api/public` | No credentials sent | 200 |
| `GET /api/admin` | No credentials sent | 401 + Basic challenge |
| `GET /api/admin` | Valid `alice`, missing role | 403 |
| `GET /api/admin` | Valid `admin`, sufficient role | 200 |
| `GET /profile` | No web session | 302 to `/login` |
| `GET /admin` | `alice` web session | 403 |
| `GET /admin` | `admin` web session | 200 |

## 5. REST APIs, Bearer Tokens, and Frontend Behavior

REST APIs typically want to return **programmatically handleable status codes** instead of HTML redirects. With OAuth2 Resource Server / Bearer tokens, the typical interpretation is:

- Missing, expired, invalid-signature, or unusable token → **401**, usually with `WWW-Authenticate: Bearer`; the response may contain error info such as `invalid_token` depending on configuration and applicable standards.
- Valid token but missing required scope/permission → **403**, possibly accompanied by a Bearer challenge carrying `insufficient_scope`.
- Valid token with sufficient permissions → proceeds to the controller.

On the client, handle them distinctly: **401** → prompt re-authentication or refresh the token according to the designed flow; **403** → display an insufficient-permissions message and do not endlessly auto-relogin; **302** → check whether it is intentional in a web flow or a sign that an API has a misconfigured entry point. With `fetch`/XHR, an HTML redirect can result in the client receiving a login page instead of the expected JSON. Do not assume every 403 can be fixed by refreshing the token.

If both UI and API run in one application, configure entry points by **chain, matcher, and authentication method**. Do not use a single "all unauthenticated requests → /login" rule for JSON APIs if the client expects 401. When writing a custom entry point returning 401 for Basic/Bearer, consider the corresponding `WWW-Authenticate` challenge; sending an empty 401 status alone may not meet protocol/client expectations.

## 6. Distinguishing Authorization Errors from CSRF and Failed Logins

**403 does not necessarily mean a missing role.** In Servlet applications using sessions/cookies, Spring Security enables CSRF protection by default for state-changing methods (such as POST/PUT/DELETE, depending on configuration). A missing or invalid CSRF token can be rejected with **403** by `CsrfFilter` before the controller is invoked, even if the account has sufficient roles. The default login page handles the token for you; when building custom HTML forms, you must supply the token according to Spring Security's mechanism.

Commonly confused scenarios:

| Symptom | Cause to check |
| --- | --- |
| `POST /submit` gets 403, while `GET` on the same resource works | Missing/invalid CSRF token; do not disable CSRF application-wide just to "fix 403". |
| Wrong form login, sent back to `/login?error` | `AuthenticationFailureHandler` handles failed login; this does not mean the controller returned 401. |
| Calling `/admin` while logged in still gets 403 | Does the actual authority have `ROLE_ADMIN`? Are `hasRole`/`hasAuthority` using the right prefix? |
| API returns login page HTML or 302 instead of 401 JSON/challenge | Check which `SecurityFilterChain` matches the URL and what entry point is configured. |
| Browser receives 200 after "going to a protected page" | Inspect the redirect chain in Network; 200 may be `/login`, not the original page. |
| Multiple redirects between login URLs | Check that the custom login URL allows access, has a controller/view, and matchers do not block it. |
| After login, still does not return to the original URL | Check `RequestCache`, session, success handler, `defaultSuccessUrl(..., true)`, or stateless configuration. |

CSRF protection errors should be fixed by sending the correct token and choosing an appropriate authentication model. Only consider excluding CSRF for endpoints that truly do not rely on automatic browser credentials (e.g., properly designed stateless bearer APIs), after assessing the risk; **HTTP Basic in a browser still carries CSRF risk because the browser can send credentials automatically**.

## 7. Ordered Diagnostic Approach

1. **Record the actual request**: method, URL, `Accept` header, `Authorization`, cookie/session, HTTP status, `Location`, and `WWW-Authenticate`. For redirects, inspect the first response before the client follows links automatically.
2. **Identify which security filter chain handles it**: compare `securityMatcher`, `@Order`, and `requestMatchers` scope. A URL hitting the wrong chain can receive a different login mechanism than expected.
3. **Identify the identity**: anonymous, Basic username, Bearer principal, or form login session? Are the credentials valid and still active?
4. **Identify the required permissions**: does the endpoint require `authenticated()`, a role, authority, scope, or method-level check (`@PreAuthorize`)? Check actual authority values, not just role names in the UI.
5. **Identify the denying filter**: insufficient permissions, CSRF, failed login, or custom handling? For POST/PUT/DELETE, check the CSRF token before concluding it is a role error.
6. **Verify the response matches the client contract**: browsers may use 302 to form login; APIs should use 401/challenge when unauthenticated and 403 when lacking permissions, per the designed mechanism.

You can enable security diagnostic logging at an appropriate level in development to understand matchers and authorization decisions, but avoid logging credentials, Bearer tokens, or sensitive cookies; disable verbose logging in production after troubleshooting.

### Rules of Thumb

- **Authentication**: "Who are you?" → if unauthenticated/unverifiable, request authentication, usually **401** for APIs or **302 to login** for form-based web.
- **Authorization**: "Are you allowed to do this?" → if authenticated but lacking permissions, usually **403**.
- **Redirect**: **302 + Location** is how browsers are directed to the login step; after following the redirect, you may get 200 on the login page.
- **Spring Security decides via filter chain configuration, entry points, access-denied handlers, and related filters**; the HTTP status is the result of that flow, not just a single `hasRole(...)` line.

### Official Documentation

- [Spring Security — Security Filters and ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Multiple SecurityFilterChain and securityMatcher](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
