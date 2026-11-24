# Separating Configuration for Web UI, REST API, and Admin Area

> **Topic:** Spring Security in a **Servlet** application, with Java 17+ and Spring Security 6 Java configuration. This lesson uses Spring Boot 3 to illustrate a runnable application; the principles of separating `SecurityFilterChain`s still apply in Servlet projects that bootstrap Spring Security without Boot.

## 1. Problem: three HTTP zones with different security needs

An application often hosts simultaneously:

- **Web UI** such as `/home`, `/dashboard`, and `/login`: users interact via a browser, log in through an HTML form, hold `SecurityContext` in an HTTP session, and need CSRF protection for state-changing operations.
- **REST API** such as `/api/public`, `/api/orders`: clients may be mobile apps, other backends, or CLIs, usually sending `Authorization` explicitly in each request; the API needs to return **401/403** rather than redirecting to an HTML page. Token-based APIs are typically designed to be stateless.
- **Admin area** such as `/admin/reports`: only accounts with admin permissions may enter, even when regular users are already validly logged in. Depending on risk, it may require MFA, re-authentication, auditing, or stricter session policies.

If a single policy is used for all URLs, common mistakes are the API redirecting to `/login`, admin routes being opened by `authenticated()`, or CSRF for the entire website being disabled just so a REST client can send POST requests.

Spring Security Servlet solves this with **multiple `SecurityFilterChain`s**, each defining a request scope and the appropriate filter set, authentication mechanism, authorization, session/CSRF/entry point.

```text
HTTP Request
    |
    v
Servlet container -> DelegatingFilterProxy -> FilterChainProxy
                                               |
                              Try SecurityFilterChains sequentially
                                               |
                        +----------------------+--------------------+
                        |                      |                    |
                   /admin/**                /api/**           Remaining (/login,
                        |                      |                /dashboard...)
                   ADMIN chain              API chain             WEB chain
                   role ADMIN               HTTP Basic demo       form login
                   uses session             stateless             uses session
                   redirect /login          401 / 403             redirect /login
                        |                      |                    |
                        +----------------------+--------------------+
                                               |
                                         Controller
```

**A request is routed by `FilterChainProxy` into the first chain whose matcher matches**. It does not run through all three chains to accumulate rules. If no chain matches, the request risks bypassing necessary security filters. That is why the example includes a final WEB chain as **fallback**.

## 2. Understanding `securityMatcher`, `requestMatchers`, and `@Order` properly

| Component | Question it answers | Effect |
| --- | --- | --- |
| `@Order(1)` on `SecurityFilterChain` bean | Which chain is evaluated first? | Chooses priority among chains |
| `http.securityMatcher("/api/**")` | Does the request belong to the **API chain**? | Limits the scope of the entire chain, including authentication and authorization filters |
| `authorizeHttpRequests(...).requestMatchers("/api/orders")` | Is the request that entered the chain permitted? | Selects the authorization rule inside the chain |
| `anyRequest()` inside a chain | How are remaining URLs in the chain handled? | Fallback rule inside the selected chain |
| Chain without its own `securityMatcher` | Where do URLs not matched by earlier chains go? | Becomes the fallback covering all remaining requests |

Chains with **overlapping** matchers do not form stacked layers of sequential protection. For example, if the unrestricted WEB chain were given `@Order(1)`, it would match `/api/**` and `/admin/**` first, preventing the API/ADMIN chains from ever being selected.

Two key principles: **specific chains go first, general chains go last**; inside `authorizeHttpRequests`, specific matchers go before the final `anyRequest()`.

For the admin area, account for both `/admin` and `/admin/**`. For the API, check whether there is a root `/api` endpoint or only URLs under `/api/`; do not assume every pattern covers every path variant. If using a special `contextPath` or `servletPath`, check how the configured Spring Security version's matchers interpret paths.

## 3. Designing the policy before writing code

We will use three illustrative accounts sharing one `UserDetailsService`:

| Username | Authorities | Purpose |
| --- | --- | --- |
| `guest` | `ROLE_USER` | Can log in to dashboard, cannot read orders or enter admin |
| `alice` | `ROLE_USER`, `orders:read` | Views dashboard and calls orders API |
| `boss` | `ROLE_ADMIN`, `orders:read` | Reads orders and enters admin area |

Endpoints:

| URL | Chain | Authorization | Unauthenticated |
| --- | --- | --- | --- |
| `GET /home` | WEB | `permitAll()` | HTTP 200 |
| `GET /dashboard` | WEB | `authenticated()` | HTTP 302 → `/login` |
| `GET /login`, `POST /login` | WEB | Form login | Displays/accepts form |
| `GET /api/public` | API | `permitAll()` | HTTP 200 |
| `GET /api/orders` | API | `hasAuthority("orders:read")` | HTTP 401 |
| `GET /admin/reports` | ADMIN | `hasRole("ADMIN")` | HTTP 302 → `/login` |
| Other URLs under `/api/**` | API | `denyAll()` | Denied |
| Other URLs under `/admin/**` | ADMIN | `hasRole("ADMIN")` | Depends on login and permission |

`ROLE_ADMIN` is the authority Spring Security uses by convention when checking `hasRole("ADMIN")`. `orders:read` is a business authority defined by the application. **Having the ADMIN role does not automatically grant every permission**; in this lesson `boss` is explicitly granted both authorities.

WEB and ADMIN can **share the login form and HTTP session**, and then ADMIN checks the role again. The API uses per-request authentication and does not use web login sessions.

## 4. Runnable example with Spring Boot 3, Java 17+

Create a Maven project with **Spring Boot 3.3.5** (a released stable version used for illustration), Java 17+, and dependencies `spring-boot-starter-web` and `spring-boot-starter-security`. No database is needed in this lesson: accounts live in `InMemoryUserDetailsManager`.

```text
segmented-security/
├── pom.xml
└── src/main/java/demo/segments/
    ├── SegmentedSecurityApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 4.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>segmented-security</artifactId>
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
```

### 4.2. `SegmentedSecurityApplication.java`

```java
package demo.segments;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SegmentedSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(SegmentedSecurityApplication.class, args);
    }
}
```

### 4.3. `SecurityConfig.java`: three clearly scoped chains

```java
package demo.segments;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
        // ADMIN: covers both /admin and /admin/**.
        http.securityMatcher("/admin", "/admin/**");
        http.authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
        );
        // /login is handled by the WEB chain; uses the logged-in web session.
        http.exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                        new LoginUrlAuthenticationEntryPoint("/login")
                )
        );
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**");
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("orders:read")
                .anyRequest().denyAll()
        );
        // HTTP Basic serves the CLI example; API does not use a session for authentication.
        http.httpBasic(Customizer.withDefaults());
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        );
        // Keep default CSRF; all API requests in this example use GET.
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        // Do not narrow securityMatcher: final chain covers remaining URLs.
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/home", "/error").permitAll()
                .anyRequest().authenticated()
        );
        http.formLogin(form -> form.permitAll());
        http.logout(logout -> logout.permitAll());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails guest = User.withUsername("guest")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_USER")
                .build();

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_USER", "orders:read")
                .build();

        UserDetails boss = User.withUsername("boss")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_ADMIN", "orders:read")
                .build();

        return new InMemoryUserDetailsManager(guest, alice, boss);
    }
}
```

The configuration above has traits you must understand clearly:

1. **ADMIN `@Order(1)`** is the highest-priority chain, matching only admin URLs. `hasRole("ADMIN")` is equivalent to checking `ROLE_ADMIN` with the default prefix. Logging in does not automatically grant admin access if the role is missing.
2. **ADMIN uses the login page from the WEB chain**: `LoginUrlAuthenticationEntryPoint("/login")` redirects unauthenticated visitors to `/login`; this URL does not match `/admin/**`, so the WEB chain displays the form and accepts `POST /login`. After authenticating through WEB, the session can carry the authentication to ADMIN. ADMIN still enforces permissions independently.
3. **API `@Order(2)`** accepts `/api/**`, using `httpBasic()` and `SessionCreationPolicy.STATELESS`. HTTP Basic here is a simple way to test with `curl`; real API deployments typically use Bearer tokens/JWTs and verify each request.
4. **WEB `@Order(3)`** does not call `securityMatcher`, making it the fallback for `/login`, `/dashboard`, and other paths. `formLogin()` provides the default login page; `logout()` handles logout along with appropriate CSRF requirements.
5. **Shared `UserDetailsService`** supplies accounts to authentication providers, yet does not force every chain to retrieve credentials the same way. In ADMIN/WEB, authentication is stored/read via the session mechanism; API is configured not to use sessions for authentication.
6. **CSRF for WEB/ADMIN is preserved**. The API example uses only GET so it does not yet need a CSRF decision for state-changing methods. Never disable CSRF across the entire application merely to make REST POSTs work.

`SessionCreationPolicy.STATELESS` means Spring Security does not create/use an HTTP session to store or retrieve `SecurityContext` for the API chain; it does not mean every component in the application is strictly forbidden from creating an HTTP session.

### 4.4. `DemoController.java`

```java
package demo.segments;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/home")
    public String home() {
        return "home:public";
    }

    @GetMapping("/dashboard")
    public String dashboard(Authentication authentication) {
        return "dashboard:" + authentication.getName();
    }

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api:public";
    }

    @GetMapping("/api/orders")
    public String apiOrders(Authentication authentication) {
        return "orders:" + authentication.getName();
    }

    @GetMapping("/admin/reports")
    public String adminReports(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
```

This `@RestController` returns plain text instead of HTML views to make testing the chains over HTTP easier. Spring Security automatically provides the default login page `GET /login`; after logging in, a browser can use the session when calling `/dashboard` or `/admin/reports`. For a real UI, you can replace the controller with MVC views, a template engine, or a corresponding frontend.

## 5. Running and verifying behavior

From the directory containing `pom.xml`, run:

```bash
mvn spring-boot:run
```

In a shell supporting `curl`, run the requests. The outputs below are **expected** with the sample configuration if the application is started on the default port 8080.

```bash
curl -s http://localhost:8080/home
# home:public

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/dashboard
# 302

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/admin/reports
# 302

curl -s http://localhost:8080/api/public
# api:public

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/orders
# 401

curl -s -o /dev/null -w '%{http_code}\n' \
  -u guest:demo123 http://localhost:8080/api/orders
# 403

curl -s -u alice:demo123 http://localhost:8080/api/orders
# orders:alice

curl -s -u boss:demo123 http://localhost:8080/api/orders
# orders:boss
```

**Verify WEB/ADMIN with a browser:** open `http://localhost:8080/admin/reports`. While unauthenticated, the browser is redirected to `/login`. Logging in as `guest/demo123` and returning to `/admin/reports` is denied (403) due to missing `ROLE_ADMIN`. Logging out through the proper flow and logging in as `boss/demo123`, the endpoint returns `admin:boss`. Logging in as `alice/demo123` allows entering `/dashboard`, but not admin.

Do not rely on `curl -u boss:demo123` alone to test ADMIN login: in this configuration **only the API chain has HTTP Basic**; WEB/ADMIN use form/session. For `POST /login`, the browser includes the CSRF token and cookie; sending a raw POST via `curl` without the token can yield 403.

### 5.1. HTTP 302 vs. 401 and 403

| Code | Scenario | Meaning |
| --- | --- | --- |
| **302** | Guest accesses `/dashboard` or `/admin/reports` | Browser flow is redirected to the login page |
| **401** | `/api/orders` without valid credentials | API authentication challenge, no redirect to form |
| **403** | `guest` has valid credentials but lacks `orders:read`; regular user enters admin | Authentication may be present, authorization denies access; 403 can also come from CSRF on state-changing requests |

If the API unexpectedly redirects to `/login`, inspect `@Order`, `securityMatcher("/api/**")`, and which authentication entry point was actually selected. If a regular user can enter admin, verify whether the request entered the ADMIN chain before changing roles.

## 6. Separating session, entry point, and CSRF

### WEB: form login and session

When `POST /login` succeeds, Spring Security creates or updates `Authentication` in `SecurityContext`; the WEB chain's mechanism saves the context to the session so the browser can reuse it on subsequent requests. The browser sends the session cookie to `/dashboard` and `/admin/reports`. Spring Security also provides session protections such as session fixation protection depending on configuration; production requires HTTPS, `Secure`/`HttpOnly`/`SameSite`, timeouts, and a logout policy.

### ADMIN: same session, stricter permissions

ADMIN and WEB can receive the same authentication from the session while ADMIN still requires `ROLE_ADMIN`. A separate chain allows adding dedicated rules in the admin zone. However, **separating chains does not automatically enable MFA, re-authentication, or a separate session timeout**. Those requirements must be designed and integrated explicitly (such as multi-factor authentication, step-up authentication, logging/auditing, and session constraints).

### API: per-request authentication

A `STATELESS` API avoids depending on web sessions when verifying an API request. In the example, Basic credentials can be authenticated per request. This is a learning approach and requires HTTPS. Production APIs typically use OAuth2 Resource Server with Bearer JWT or opaque tokens.

**CSRF does not depend solely on whether sessions exist.** Browsers can automatically send cookies and sometimes even HTTP Basic credentials; therefore you cannot conclude "REST API = safe to disable CSRF". If only clients explicitly sending a Bearer token in a header are accepted and the server rejects browser-auto-sent credentials, you can configure CSRF specifically for the API chain under that architecture. Cookie-based WEB/ADMIN needs protection for state-changing operations.

An **alternative fragment**, when the API switches completely to Bearer JWT, is:

```java
// Fragment inside apiChain(), replacing the existing httpBasic().
// Only appropriate when the API does not accept cookies or browser-auto-sent credentials.
http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
);
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
http.csrf(csrf -> csrf.disable());
```

This snippet **does not run standalone**: it needs `spring-boot-starter-oauth2-resource-server`, trusted issuer/JWK or `JwtDecoder` configuration, and valid tokens. JWT scopes are by default converted to `SCOPE_<scope>` authorities; if you keep `hasAuthority("orders:read")`, ensure the converter/token supplies that exact authority or adjust the rule accordingly. Never treat roles/permissions in an unverified client payload as trusted permissions.

## 7. URL authorization vs. method authorization

`authorizeHttpRequests` protects URLs in the filter chain before controllers run. When business logic can also be invoked by jobs or other services, you can consider method security (`@EnableMethodSecurity` and `@PreAuthorize`), keeping in mind Spring AOP/proxy mechanisms and caveats such as self-invocation.

```java
// Fragment inside a @Configuration class:
@EnableMethodSecurity

// Fragment on a method of a Spring-managed bean:
@PreAuthorize("hasAuthority('orders:read')")
public OrderSummary readOrders() {
    // business logic
}
```

These are **two fragments in different places**, not a complete Java class; `OrderSummary` is only an illustrative type. Do not assume splitting `SecurityFilterChain`s replaces service-layer policies when business operations need protection independent of HTTP URLs.

## 8. When are multiple chains necessary?

**Use multiple chains** when URL groups differ substantially in authentication mechanism, entry point (HTML redirect vs. HTTP 401), session policy, CSRF, or custom security filters.

**A single chain can suffice** when all URLs share the same form login/session/filters and differ only in roles/permissions. In that case, writing multiple `requestMatchers` inside one `authorizeHttpRequests` is usually easier to understand:

```java
// Alternative fragment illustrating a single chain; do not merge into section 4's config.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .requestMatchers("/reports/**").hasAuthority("reports:read")
        .anyRequest().authenticated()
);
http.formLogin(Customizer.withDefaults());
```

Do not create one `SecurityFilterChain` per endpoint merely because each endpoint demands a different role. The complexity of multiple chains lies in matchers, ordering, shared filter/state, and ensuring no URL slips past the policy.

## 9. Common errors and diagnostic process

| Symptom | Cause to check | Remediation |
| --- | --- | --- |
| API redirects to HTML login instead of 401 | WEB chain matched before API or wrong entry point | Check `@Order`, `securityMatcher`, Basic/Bearer mechanism |
| Regular user can enter admin | ADMIN chain not selected or missing `hasRole("ADMIN")` | Inspect actual URL, matcher, rule, and current authorities |
| API POST returns 403 | CSRF enabled or authorization denied | Check which filter denied it; configure CSRF per credentials and client |
| `POST /login` returns 403 | Missing CSRF token/cookie when sending request manually | Use browser flow or send proper token in tests |
| API request works with WEB cookie and no Authorization | API still reads session or URL matched wrong chain | Check `STATELESS`, chain order, and security context repository |
| `ROLE_USER` fails `hasRole("ADMIN")` | This is intentional denial | Check role mapping; do not add a bypass |
| Has `ADMIN` yet `hasRole("ADMIN")` returns 403 | Default authority must be `ROLE_ADMIN` | Grant consistent role/authority or configure prefix |
| Sensitive URL unprotected by Spring Security | No security chain matched, missing fallback | Add fallback; test every path including root `/admin` |
| Admin form redirects to `/login` but page does not appear | `/login` captured by another chain or web chain lacks form login | Keep `/login` and `POST /login` inside the WEB chain |
| Custom filter runs twice | Registered in both Servlet container and Spring Security chain | Verify filter registration location and initialization flow |

When debugging, follow this order: **(1) actual URL and servlet path → (2) selected security chain → (3) authentication/session/token → (4) authorities → (5) rules and CSRF → (6) HTTP entry point/response**.

In development you can use:

```properties
logging.level.org.springframework.security=DEBUG
```

This is an `application.properties` configuration fragment to observe Spring Security logs, not a Java program. Never log passwords, Bearer tokens, or session cookies, especially in production.

## 10. Knowledge self-check

1. **Why is WEB's `@Order(3)` the fallback?** Because the WEB chain does not narrow `securityMatcher`, so it can match remaining URLs after ADMIN/API.
2. **Are `http.securityMatcher("/api/**")` and `requestMatchers("/api/orders")` the same?** No: the first selects the *chain*, the second selects a *rule* inside the chain.
3. **What does `guest` get when calling the orders API with valid Basic credentials?** 403 due to missing `orders:read`.
4. **If `boss` sends Basic to `/admin/reports`, is it accepted automatically?** Not in this example: ADMIN does not enable HTTP Basic, and instead redirects to WEB's form login.
5. **Can `guest` log in via WEB and then enter ADMIN?** No, the session only establishes identity; ADMIN still requires `ROLE_ADMIN`.
6. **Is disabling CSRF on WEB the right way to make API POSTs work?** No. Handle CSRF per client group, credential type, and associated chain.
7. **What happens if an undeclared `GET /api/unknown` is added?** The API chain is selected, and `denyAll()` rejects it.
8. **Why might the ADMIN role not be enough to read orders?** Roles and permissions are distinct authorities; the example grants `orders:read` explicitly.

## 11. Pre-deployment checklist

- [ ] Map actual prefixes and endpoints, including login/logout, error, static resources, context path, and root paths.
- [ ] Place specific chains before the fallback chain; check overlaps and unmatched routes.
- [ ] Define separate authentication mechanisms, entry points, and session policies for browser, API, and admin.
- [ ] Test permissions with real authorities, including logged-in users lacking permissions.
- [ ] Keep CSRF for cookie-based UIs; evaluate CSRF for APIs based on how clients send credentials.
- [ ] Ensure the login page and login processing URL actually belong to the chain with form login.
- [ ] Add tests for 200/302/401/403 as well as root `/admin` and `/api` paths if the application handles them.
- [ ] For sensitive admin areas, implement MFA, re-authentication, logging, and session controls according to real requirements.
- [ ] Re-verify when using reverse proxies, path rewriting, CORS, or custom filters.

**Key takeaway:** `@Order` determines **chain evaluation order**; `securityMatcher` determines **which chain receives a request**; `requestMatchers` determines **permission rules inside the chain**. Separating these three levels is the foundation for a Servlet application to properly protect its web UI, REST API, and admin area.