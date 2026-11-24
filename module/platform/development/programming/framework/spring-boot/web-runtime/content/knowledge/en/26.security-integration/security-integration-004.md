# Distinguishing HTTP 401, 403, and Login Redirects in the Spring Boot Web Runtime

## 1. Lesson Objectives

When a request reaches a protected endpoint in Spring Boot, the system must answer two **different** questions:

1. **Authentication:** Does the system already know the caller's identity? Are the credentials valid?
2. **Authorization:** Given that identity, does the caller have permission to perform the action on the specific resource?

From these arise three common behaviors:

- **401 Unauthorized:** the client did not provide valid authentication proof, or the proof was rejected. The status name contains the word “Unauthorized”, yet by HTTP semantics it typically indicates **valid authentication is required**.
- **403 Forbidden:** the server understands the request yet **refuses to allow** the operation. A user may be logged in with a valid account yet lack permission; additionally, other protections such as **CSRF** can also produce 403.
- **302 Found → login page:** in web applications using **form login and session cookies**, unauthenticated visitors are typically **redirected** to `/login`. This initiates browser-based authentication rather than returning 401.

This article uses **Spring Boot, Spring Security, and Spring MVC (Servlet stack)** to show what conditions produce 401/403/redirects, the roles of `AuthenticationEntryPoint` and `AccessDeniedHandler`, how to design separately for REST APIs vs traditional web pages, and how to test using Spring Security Test.

Goal after this lesson: when encountering 401, 403, 302, or redirect loops, you can pinpoint **which layer returned the response and why**, instead of “fixing” every error by disabling Spring Security or adding `permitAll()`.

## 2. Quick Comparison Table

| Scenario | API using HTTP Basic/Bearer | Browser using form login | Meaning |
| --- | --- | --- | --- |
| No credentials sent to an auth-required resource | Usually **401** + appropriate challenge | Usually **302** to `/login` | Authentication must begin |
| Wrong password or invalid token | Usually **401** | Failed login POST, usually **302 /login?error** or renders error message | Authentication failed |
| Valid login, missing role/authority for resource | **403** | **403** or configured access-denied page | Identity known, but permission not granted |
| POST request using cookie, missing CSRF token | May be **403** if chain enables CSRF | Usually **403** | CSRF protection rejected it; cannot infer “missing role” |
| Logged in, valid endpoint, sufficient permission | **200** or appropriate business code | **200** or workflow redirect | Security lets request proceed |
| Accessing nonexistent URL after passing security | Usually **404** | Usually **404** | Routing/resource lookup differs from authentication/authorization |

**Warning:** the table describes **common configurations**, not immutable rules for every application. `SecurityFilterChain`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, method security, CORS, CSRF, API gateways, and controller exception handlers can all alter status codes. A `403` **does not prove by itself** that the user is logged in, and a `302` redirect **does not prove** login succeeded.

### 2.1. HTTP 401 and the `WWW-Authenticate` Header

Under HTTP semantics, 401 indicates the request lacks valid credentials for the target resource and the response must include an appropriate **`WWW-Authenticate` challenge**. For example, HTTP Basic:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

The realm name is illustrative and can vary by configuration; the body may be empty, HTML, or JSON depending on the stack. Browsers may pop up a username/password prompt upon receiving a Basic challenge, while API clients use the challenge to decide how to supply credentials.

With OAuth 2.0 Resource Server / Bearer tokens, a typical challenge is:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

In some cases, a Bearer token lacking sufficient scope can return **403** with `WWW-Authenticate: Bearer error="insufficient_scope"` and appropriate scope information. **Do not lump all OAuth errors together with Basic**; Spring Security uses the entry point and access-denied handler corresponding to the configured authentication method.

Spring Security HTTP Basic also has specific behavior for certain AJAX requests: the official documentation notes that if a request includes `X-Requested-By: XMLHttpRequest`, the 401 challenge/body can be suppressed/adjusted to avoid browser Basic login dialogs. Therefore **when testing the Basic challenge itself**, use a plain request without adding arbitrary client headers.

### 2.2. HTTP 403 Is Not Only for Roles

A 403 can come from:

- An authenticated user lacking `ROLE_ADMIN`, an authority, a permission, tenant ownership, or a policy condition.
- Missing, invalid, or expired CSRF token on a state-changing request.
- A gateway/WAF/ingress blocking the request before Spring Boot.
- An IP allowlist, custom rate-limit policy, or application-designed denial logic returning 403.
- Method security, controller/service logic, or a resource policy with an access-denied handler.

So when encountering 403, **inspect the response source**: security filter, CSRF, authorization, service, gateway, or exception handler. Do not “fix” it by granting `ADMIN` or disabling CSRF before identifying the root cause.

## 3. Spring Security Mechanics: What Decides 401, 403, or Redirect?

In a Servlet application, Spring Security inserts a filter chain into the request pipeline via `FilterChainProxy` and `SecurityFilterChain` beans. Key components:

- **Authentication filters** (e.g., `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, Bearer token filter) inspect credentials and create an `Authentication` object.
- **SecurityContext** holds the current request's authentication info per Spring Security policy.
- **AuthorizationFilter** and/or method security evaluate policies such as `authenticated()`, `hasRole("ADMIN")`, or authorities/scopes.
- **ExceptionTranslationFilter** translates security exceptions (`AuthenticationException` and `AccessDeniedException`) into appropriate HTTP actions.
- **AuthenticationEntryPoint** initiates authentication: it may return 401 with a Basic or Bearer challenge, or redirect to a login page.
- **AccessDeniedHandler** handles requests denied when the identity is already authenticated according to security filter semantics.

Conceptual flow:

```text
HTTP request
    |
    v
Matching SecurityFilterChain for request
    |
    +--> Authentication: are credentials valid?
    |          |
    |          v
    +--> Authorization: permitted for endpoint/object?
               |
               +--> Allowed ---> Controller ---> business 2xx/3xx/4xx/5xx
               |
               +--> AuthenticationException
               |           |
               |           v
               |      AuthenticationEntryPoint
               |        Basic API: 401 + WWW-Authenticate
               |        Web Form: 302 -> /login
               |
               +--> AccessDeniedException
                           |
                   Anonymous/unauthenticated?
                      /             \
                    Yes              No
                     |                |
              EntryPoint       AccessDeniedHandler
               401/302             usually 403
```

**Common pitfall:** When an **anonymous** user hits `hasRole("ADMIN")`, `AuthorizationFilter` may throw `AccessDeniedException`. However, `ExceptionTranslationFilter` recognizes that the caller is unauthenticated and invokes the **entry point**, rather than necessarily returning 403. With a Basic API, anonymous normally gets 401; with form login, anonymous normally gets redirected to login.

If the caller is already authenticated yet still lacks permission, the access-denied handler usually returns 403. This is why “missing role” produces **different status codes** for anonymous vs logged-in users.

`ExceptionTranslationFilter` does not compute permissions itself. It only catches and translates security exceptions thrown by filters downstream of it. An exception already caught by `@ControllerAdvice` or another layer and turned into a custom HTTP body might bypass this translation path. Place security rules in **filters/method security** instead of throwing arbitrary exceptions hoping default behavior stays identical.

## 4. Authentication vs Authorization in Code

Common rules:

```java
// Snippet inside authorizeHttpRequests, not a standalone class.
.requestMatchers("/profile").authenticated()
.requestMatchers("/admin").hasRole("ADMIN")
.requestMatchers("/reports").hasAuthority("REPORT_READ")
.anyRequest().denyAll()
```

- `authenticated()`: the caller must be considered authenticated by Spring Security under the policy.
- `hasRole("ADMIN")`: Spring Security looks for `ROLE_ADMIN` by default; **do not** pass `"ROLE_ADMIN"` to `hasRole` in standard setups, since the prefix is added automatically.
- `hasAuthority("REPORT_READ")`: matches the exact authority name; does not prepend `ROLE_`.
- `denyAll()`: denies even authenticated callers; anonymous callers may be sent to the entry point.
- `permitAll()`: does not require login for that matcher; other protective filters, such as CSRF on unsafe methods, may still apply.
- **Object-level** permissions (only the owner can view an order) are not enforced merely because `/orders/{id}` requires `authenticated()`. The service must check ownership/tenant/ACL rather than relying on hard-to-guess IDs.

Example:

```text
GET /orders/123
Authentication: user = alice

If order 123 belongs to alice -> allowed.
If order 123 belongs to bob -> denied by policy,
not automatically readable just because alice is logged in.
```

For existing objects whose existence should not be disclosed, an application may return **404 instead of 403** as an anti-enumeration policy. Apply this consistently; do not conflate “unauthorized” with “not found” in internal logs/metrics.

## 5. Two Common Web Runtime Patterns

### 5.1. REST APIs: Usually Require 401/403, Not HTML Login Redirects

An API serving mobile apps, frontend SPAs, or service-to-service callers usually needs **machine-readable responses**:

```text
GET /api/profile
  No credentials     -> 401 (+ auth challenge)
  Wrong credentials  -> 401
  Valid credentials  -> 200

GET /api/admin
  Unauthenticated    -> 401
  Regular USER       -> 403
  ADMIN              -> 200
```

If an API accidentally returns `302 Location: /login`, many HTTP clients **automatically follow the redirect** and receive an HTML login page with a final 200 status. The frontend may try to parse HTML as JSON, causing errors like `Unexpected token '<'`. Logs and metrics might only show 200 on the final request and miss the initial 302.

Do not just send an `Accept: application/json` header hoping the framework picks 401 on every endpoint. When the same app serves both APIs and browser UI, explicitly design **security matchers and entry points** so behavior stays predictable per route.

For JWT/Bearer, use the official Spring Security OAuth 2.0 Resource Server rather than hand-parsing tokens with string manipulation; 401/403 and challenges follow Bearer semantics. The runnable example in Section 8 uses **HTTP Basic** solely for ease of demonstration, not as a recommendation to use Basic with static passwords in production.

### 5.2. Server-Rendered Web Pages: 302 Sends Unauthenticated Users to Login

For UI using browsers/session cookies:

```text
1. Browser -> GET /app/private
2. Spring Security: not logged in
3. Response: HTTP 302, Location: /login
4. Browser -> GET /login
5. Spring Security renders login page
6. User POST /login with username/password + CSRF token
7. Login succeeds -> redirected per success handler
8. Browser accesses permitted page
```

The redirect **starts the login process**; it does not verify identity. If a user has a valid session yet lacks a role for `/app/admin`, Spring Security normally **returns 403**, rather than redirecting back to `/login` to re-enter the same account.

Factors affecting redirects:

- `LoginUrlAuthenticationEntryPoint` determines where authentication starts for form login.
- Request cache can store a **saved request** to send the user back to the original resource after login. Setting `defaultSuccessUrl("/app/private", true)` intentionally ignores the saved request and always redirects to a fixed URL on success.
- Wrong `X-Forwarded-Proto`, host, proxy prefix, or context path can produce a broken `Location`, HTTPS→HTTP downgrades, redirect loops, or missing session cookies.
- Spring Security's auto-generated login page only exists when using default form login; if you configure a custom `loginPage("/login")`, **the application must render that page itself**.
- `/login` and its static assets must be permitted; if the login page itself is blocked by security rules, a redirect loop easily occurs.

## 6. Understanding Login Failure and Logout Responses

**Wrong password on a Basic API:** usually 401; the challenge tells the client valid credentials are needed. **Wrong password on an HTML form POST:** typically redirects to `/login?error` in the default configuration, or displays an error via a custom failure handler. This is a browser flow, not identical to API 401.

**Successful login:** typically a 302 redirect to the saved request or default success URL, while the session/security context is managed per policy. Here 302 is a **login success outcome**; it does not mean the same thing as a 302 when an anonymous user is sent to login. Always examine the **original request** and `Location`.

**Logout:** with Spring Security's default CSRF enabled, logout requires a POST with a CSRF token; after logout it can redirect to `/login?logout`. Never allow logout via GET casually in browser-authenticated apps; for stateless API tokens, logout/revocation strategies differ from session logout.

**Never infer from a single HTTP code:** to verify whether a user is authenticated, inspect the security context and handle results per auth contract rather than checking whether the final response was `200` or `302`.

## 7. Basic API and Form Login in the Same App: Why Two SecurityFilterChains?

If you enable both simultaneously:

```java
http.httpBasic(Customizer.withDefaults())
    .formLogin(Customizer.withDefaults());
```

on **a single shared filter chain**, Spring Security may use content negotiation or request-based entry-point selection to pick a Basic challenge vs a login redirect. While valid for many apps, it can cause surprises when frontends send varying `Accept` headers or browsers fetch APIs.

**Clear separation pattern:** split into:

- `/api/**` chain: HTTP Basic only; stateless; **401** when credentials are missing, **403** when authenticated without role.
- Remaining chain for `/app/**` and login: form login; session-based; **302** for anonymous, **403** when logged in without authority.

With multiple `SecurityFilterChain` beans, Spring Security chooses the matching chain by `@Order`. Each request goes through only **the selected chain**, not the union of rules across all chains. `securityMatcher(...)` defines the scope of the **filter chain**, while `requestMatchers(...)` inside `authorizeHttpRequests` sets **authorization rules within that chain**.

Always include a fallback chain so no route is accidentally left unprotected. In the example, the default chain has `anyRequest().denyAll()` while permitting required login routes. When new endpoints are added to the project, developers must explicitly define their policy instead of leaving them public by accident.

## 8. Runnable Example: Spring Boot 3.5.16 + Java 17 + Spring Security

The example uses **Spring MVC** (embedded Tomcat), **HTTP Basic** for the API, and **default form login** for browsers. Spring Boot 3.5.16 is chosen to pin a stable API set for the lab; it is a released version, though **Spring Boot 3.5.x has reached end of OSS support**. New production projects should use a **supported Spring Boot line** with current patches; when upgrading to Boot 4.x, check compatible starter/test packages and APIs.

Example accounts (for local demo only):

| User | Demo password | Roles |
| --- | --- | --- |
| `reader` | `reader-pass` | `ROLE_USER` |
| `admin` | `admin-pass` | `ROLE_ADMIN`, `ROLE_USER` |

**These are fixed sample credentials for local learning; never deploy them to the internet or use them in production.** Passwords are encoded with BCrypt when constructing `UserDetailsService`, yet hardcoded passwords remain a production anti-pattern.

### 8.1. Project Structure

```text
security-status-demo/
├─ pom.xml
└─ src/
   ├─ main/
   │  └─ java/com/example/demo/
   │     ├─ SecurityStatusApplication.java
   │     ├─ SecurityConfiguration.java
   │     └─ DemoEndpoints.java
   └─ test/
      └─ java/com/example/demo/
         └─ SecurityStatusApplicationTest.java
```

### 8.2. `pom.xml`

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-status-demo</artifactId>
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
```

Maven requires access to appropriate repositories to download dependencies. If generated via Spring Initializr/Maven Wrapper, keep your organization-approved wrapper and build config; when moving to a newer supported parent, update versions and API compatibility together.

### 8.3. Main Class

**`src/main/java/com/example/demo/SecurityStatusApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityStatusApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityStatusApplication.class, args);
    }
}
```

### 8.4. Two Filter Chains and Demo Accounts

**`src/main/java/com/example/demo/SecurityConfiguration.java`**

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/profile").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache -> cache.disable());

        // Do not disable CSRF in demo: both APIs use GET only.
        // For POST/PUT/DELETE, evaluate CSRF based on how clients send credentials.
        return http.build();
    }

    @Bean
    SecurityFilterChain browserSecurity(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/app/admin").hasRole("ADMIN")
                .requestMatchers("/app/private").authenticated()
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/app/private", true)
            );

        // Spring Security keeps default CSRF protection.
        // Default form login is rendered automatically by Spring Security.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN", "USER")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
```

**Explanation:**

1. `@Order(1)` + `securityMatcher("/api/**")` ensures all API requests go through the chain with `httpBasic` and are not intercepted by the form-login entry point to redirect to HTML.
2. `hasRole("ADMIN")` on `/api/admin` and `/app/admin` matches the `ROLE_ADMIN` authority. `reader` is valid yet only has `ROLE_USER`, so it gets 403.
3. `/api/profile` and `/app/private` require authentication, without requiring the admin role.
4. `SessionCreationPolicy.STATELESS` prevents Spring Security from creating/using an `HttpSession` to store `SecurityContext` for the API. Basic clients send credentials on every request. It **does not make the entire application stateless**: the browser chain still uses form login/sessions.
5. `requestCache(cache -> cache.disable())` avoids saving requests for the API, because API clients retry themselves once they have credentials.
6. **CSRF stays enabled by default in both chains**. The example APIs are GET-only, so no relaxation is needed. If adding state-changing APIs later, choose the exact CSRF policy for cookies, Basic, bearer tokens, and client types; never copy `csrf.disable()` blindly.
7. The default browser chain catches URLs outside `/api/**`, renders the default login form at `/login`, and protects private and admin pages. `defaultSuccessUrl(..., true)` keeps post-login test behavior independent of saved requests.
8. `anyRequest().denyAll()` prevents new routes from accidentally becoming public. When adding assets, health endpoints, or custom login/logout pages, intentionally grant access to those exact URLs.
9. BCrypt encodes demo passwords; production needs a user store/identity provider plus credential management, resets, MFA, auditing, session fixation protection, rate limiting, secrets, and account lifecycle.
10. `@EnableWebSecurity` is omitted in the demo because Spring Boot/Spring Security auto-configuration already provides the foundation for these `SecurityFilterChain` beans. Avoid accidentally declaring overlapping filter chains for the same URLs.

**Note on logout:** the example focuses on GET and form login. If logout is needed, enable/configure Spring Security's standard `logout()`, protect POST logout with CSRF, and re-test access after logout; never just delete a cookie while skipping invalidation/security context clearing.

### 8.5. Controller for Easy Observation

**`src/main/java/com/example/demo/DemoEndpoints.java`**

```java
package com.example.demo;

import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoEndpoints {

    @GetMapping(value = "/", produces = MediaType.TEXT_PLAIN_VALUE)
    public String index() {
        return "Security status demo\n";
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName(), "area", "api");
    }

    @GetMapping("/api/admin")
    public Map<String, String> apiAdmin(Authentication authentication) {
        return Map.of("user", authentication.getName(), "role", "admin");
    }

    @GetMapping(value = "/app/private",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String privatePage(Authentication authentication) {
        return "Private page for " + authentication.getName() + "\n";
    }

    @GetMapping(value = "/app/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String adminPage(Authentication authentication) {
        return "Admin page for " + authentication.getName() + "\n";
    }
}
```

- `Authentication` comes from the request after passing security filters, never from a query parameter. Never use `?user=admin` to decide permissions.
- `@RestController` returns response bodies; the plain strings are not template names. The default login page is HTML generated separately by Spring Security; the demo does not need Thymeleaf.
- `Map<String,String>` serializes to JSON via Jackson. JSON field order is not fixed; tests should assert fields/values rather than comparing raw JSON strings by key order.
- The controller has no homegrown `if (isAdmin)`. Security rules live in the filter chains, and production still needs service-layer authorization when data depends on owner/tenant or object IDs.

### 8.6. Running the Application

With JDK 17+ and Maven installed:

```bash
java -version
mvn spring-boot:run
```

If using the Maven Wrapper from Spring Initializr:

```bash
./mvnw spring-boot:run
```

On Windows: `mvnw.cmd spring-boot:run`. By default, the app listens on `http://localhost:8080` unless port configuration overrides it. The sample responses below assume no additional `application.properties`, proxies, or security filters are present.

### 8.7. API: Testing 401, 403, and 200 with curl

**No credentials:**

```bash
curl -i http://localhost:8080/api/profile
```

Expected: **HTTP 401**, `WWW-Authenticate` header starting with `Basic`, not a redirect to `/login`. Error body depends on Spring Security/Boot and may be empty; do not assume a mandatory JSON error body.

**Wrong password:**

```bash
curl -i -u reader:wrong \
  http://localhost:8080/api/profile
```

Expected: **HTTP 401**; no profile data returned.

**Correct password:**

```bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/profile
```

Expected: HTTP **200** with JSON containing `"user":"reader"` and `"area":"api"`.

**Logged in but missing ADMIN role:**

```bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/admin
```

Expected: **HTTP 403**. This is an authorization error, not a reason to send the browser to a login page or return 401.

**Valid ADMIN:**

```bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin
```

Expected HTTP **200**, JSON containing `"user":"admin"` and `"role":"admin"`.

**Basic security note:** The Authorization header carries credentials in Base64, **not encrypted**. **HTTPS** is mandatory on real networks; never log Authorization headers, never use demo passwords outside localhost, and never leave real credentials in shell history on shared machines. For production APIs, typically evaluate bearer tokens/OAuth2 and credential rotation per architecture.

### 8.8. Browser: Observing Redirects and 403

Without a login session:

```bash
curl -i http://localhost:8080/app/private
```

Expected HTTP **302** (or appropriate redirect per config) with `Location` pointing to `/login`. The value may be a relative path or an absolute URL depending on framework/container/proxy; tests should assert the login route without unnecessarily hardcoding the host.

In a browser, open:

```text
http://localhost:8080/app/private
```

You will be redirected to the default login page. Log in with `reader` / `reader-pass`; upon successful login, the demo configuration redirects to `/app/private` and displays text containing the username.

While the browser is logged in as `reader`, visit:

```text
http://localhost:8080/app/admin
```

Expected **403**, without redirecting back to `/login`. Log in again with the `admin` account (for example in a new browser session) and `/app/admin` will be allowed and return 200.

**Why can `curl -L` be misleading?** If you run `curl -L` on an anonymous request, the client follows `Location` to the login page and displays the final page's body. You may see HTTP 200 for the login page and mistakenly assume `/app/private` granted access. Use `curl -i` or `curl -v` **without following redirects** when investigating the initial status.

## 9. Automated Testing with MockMvc + Spring Security Test

The test goal is to verify that policies are enforced at the HTTP/security layer, not only in controllers. The project already includes the `spring-security-test` dependency.

Create **`src/test/java/com/example/demo/SecurityStatusApplicationTest.java`**:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityStatusApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousApiGets401AndBasicChallenge() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                startsWith("Basic")
            ));
    }

    @Test
    void wrongBasicPasswordGets401() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctBasicPasswordGets200() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("reader"));
    }

    @Test
    void authenticatedApiUserWithoutRoleGets403()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanCallAdminApi() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("admin"));
    }

    @Test
    void anonymousBrowserRequestRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/app/private"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                HttpHeaders.LOCATION, endsWith("/login")
            ));
    }

    @Test
    void anonymousAdminPageAlsoStartsLogin() throws Exception {
        mvc.perform(get("/app/admin"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                HttpHeaders.LOCATION, endsWith("/login")
            ));
    }

    @Test
    void authenticatedNonAdminGets403InBrowser()
            throws Exception {
        mvc.perform(get("/app/admin")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedUserCanSeePrivatePage() throws Exception {
        mvc.perform(get("/app/private")
                .with(user("reader").roles("USER")))
            .andExpect(status().isOk());
    }

    @Test
    void loginPostWithoutCsrfGets403() throws Exception {
        mvc.perform(post("/login")
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validLoginPostWithCsrfRedirectsToPrivatePage()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/app/private"));
    }
}
```

Run:

```bash
mvn test
```

In a project generated with the Maven wrapper, you can use `./mvnw test` or `mvnw.cmd test` on Windows. With the exact configuration and versions in `pom.xml`, **11 tests are expected to pass**. These are expected results for learners to run themselves, **not a claim that this article was executed against a specific repository**.

**Key points about the tests:**

- `.with(httpBasic(user, password))` builds a Basic header so the filter actually authenticates the account against `UserDetailsService`.
- `.with(user("reader").roles("USER"))` is a **test helper** setting an authenticated user in the security context; it **does not test password verification**. Use it to test authorization, not as a replacement for testing Basic passwords or login POSTs.
- `.with(csrf())` supplies a valid CSRF token for POSTs in MockMvc. Without `csrf()`, POST `/login` is not a valid login request under the demo's security policy.
- For an anonymous visit to the admin page, `AccessDeniedException` triggers the **entry point**, so it redirects to login instead of returning 403.
- `defaultSuccessUrl("/app/private", true)` makes the post-login redirect target fixed, keeping the `redirectedUrl` test independent of request caching.
- The first test checks both `401` and `WWW-Authenticate`; the sixth checks **Location to the login page**; the others clearly distinguish “authenticated yet lacking permission” from “unauthenticated”.

Add integration tests with a **real HTTP connector**, proxy/ingress, and browser if the app uses cookies, CORS, OAuth redirects, and HTTPS termination. MockMvc verifies filter chain/dispatcher logic, yet does not prove all headers are preserved by proxies/CDNs.

## 10. CSRF: Why Can You Get 403 Even Before Logging In?

Spring Security protects **state-changing HTTP methods** such as POST/PUT/PATCH/DELETE with CSRF by default when a Servlet app uses the default policy. The CSRF filter can reject a request **before it reaches the controller and before role-based authorization results appear**.

Example:

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=reader&password=reader-pass
```

Without a valid CSRF token, the demo returns **403**, not 302 to the login page and not 401 for bad password. This is a **CSRF protection failure**, not a sign that `reader` lacks a role.

With a real login form, `GET /login` generates an HTML form with a hidden token via Spring Security integration; the browser submits the token back on POST. With a custom login page, the developer must ensure the token is included in the form properly. After login/logout, the token may be rotated/cleared by Spring Security; SPA frontends must obtain the fresh token per their architecture.

**Never disable CSRF app-wide just to turn 403 into 200.** Determine:

1. Does the endpoint belong to a stateless Bearer API or a browser session/cookie flow?
2. Did the request send the CSRF token in the right field/header with a valid cookie/session?
3. Was a CORS preflight OPTIONS blocked before authentication due to filter chain configuration?
4. Did the CSRF token expire, start a new session, cross login/logout, or change cookie path/domain?
5. Is it truly a role-based `AccessDeniedException` rather than `InvalidCsrfTokenException` or `MissingCsrfTokenException`?

**HTTP Basic is not automatically immune to CSRF risks** just because it is called “API”: browsers can automatically resend cached Basic credentials in certain situations. If disabling CSRF on Basic routes with write operations, carefully assess the client/credential model; prefer Bearer tokens explicitly attached by JavaScript/API clients for stateless APIs when appropriate.

## 11. Request Cache, Sessions, and Redirect Loops

Form login typically maintains state across requests via a session cookie. When an anonymous user requests a private page, `RequestCache` can save the original request and redirect the user back after successful login. If the session cookie is not sent back, the browser can experience:

```text
GET /app/private -> 302 /login
GET /login -> 200 login page
POST /login -> logs in
GET /app/private -> 302 /login again
... loop ...
```

Causes to investigate:

- The session cookie is not saved/sent due to domain, `Path`, `Secure`, `SameSite`, timeout, or browser privacy settings.
- The app runs behind a TLS-terminating reverse proxy, yet `X-Forwarded-Proto/Host/Prefix` are not handled properly → redirects point to `http`/wrong host/path.
- Cookie was issued for a different domain/path than the public URL, or multiple replicas do not share a session store/sticky routing.
- Custom login page `/login` also falls under an `authenticated` rule → redirects to itself.
- Custom authentication success handler builds a wrong redirect or stale saved request.
- CORS/cross-site credentials and cookie policies are incompatible with a frontend SPA.

**Never fix a redirect loop by changing every rule to `permitAll()`.** Inspect which chain matched the request, status/Location at each hop, `Set-Cookie` and `Cookie`, and session persistence, then fix the exact boundary.

In the example, the API chain uses `STATELESS` and no request cache; the browser chain uses form login and sessions. Never apply `SessionCreationPolicy.STATELESS` to a browser chain expecting default session login to persist across requests.

## 12. Customizing 401/403 Responses for REST APIs

A product may want a consistent JSON body:

```json
{
  "status": 403,
  "code": "ACCESS_DENIED",
  "message": "You do not have permission for this resource"
}
```

In Spring Security, the right places are:

- **`AuthenticationEntryPoint`**: handles initiating authentication — returns 401 (with the scheme-appropriate challenge), not a redirect for API routes.
- **`AccessDeniedHandler`**: handles insufficient permission for an authenticated caller — returns 403.
- **`@ControllerAdvice`**: handles validation, business errors, and server errors from controllers/services; do not treat it as a guaranteed replacement for filter-level security exceptions.

The following snippet illustrates **only response routing**, without full JSON serialization/security scheme handling:

```java
// Illustrative snippet inside an API SecurityFilterChain.
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint((request, response, error) -> {
        response.setStatus(401);
        response.setContentType("application/json");
        response.getWriter().write(
            "{\"status\":401,\"code\":\"AUTH_REQUIRED\"}"
        );
    })
    .accessDeniedHandler((request, response, error) -> {
        response.setStatus(403);
        response.setContentType("application/json");
        response.getWriter().write(
            "{\"status\":403,\"code\":\"ACCESS_DENIED\"}"
        );
    })
);
```

**Important:** this snippet **must not be copied as-is into a production Basic/Bearer chain** without preserving the proper `WWW-Authenticate` challenge. It is intentionally incomplete; if using a custom entry point for Basic, delegate or emit a valid `Basic realm="..."` challenge, or wrap error formatting around an appropriate entry point. For Bearer, follow OAuth2 challenge/error rules. Never expose specific bad password details, internal tokens, stack traces, or sensitive permission lists in responses.

Similarly, if you want a custom 403 page for browsers:

```java
// Snippet in a browser security chain.
http.exceptionHandling(ex -> ex
    .accessDeniedPage("/access-denied")
);
```

The application must provide the `/access-denied` route/view and a `permitAll()` or appropriate permission policy so users can view it. Never redirect all 403s to login: an authenticated user lacking a role needs an access-denied message, not an endless login prompt.

## 13. CORS, 401/403, and Browser Errors

A frontend SPA running at `https://ui.example.com` calling an API at `https://api.example.com` is **cross-origin**. The browser may send an `OPTIONS` preflight request before the main request. If a security filter requires authentication before CORS processing runs, preflight requests typically **lack the session cookie/Authorization header you expect**, so they get blocked; the console may report a CORS error, 401/403, or `Failed to fetch`.

Distinguish between:

- **401 from API:** the server received the main request and requires authentication; the body/headers might still be unreadable to browser JS due to CORS policy.
- **403 from CSRF:** a state-changing request is missing a token (not the same as CORS).
- **CORS failure:** the browser refuses to expose the response to JavaScript due to mismatched headers/preflight, even though calling the URL via curl succeeds.
- **Redirect to HTML login:** may cross to a different origin/host and get blocked by the browser; or the frontend receives HTML instead of JSON if the redirect is followed.

CORS policy should allowlist only permitted public origins and handle preflight **before authentication** using proper Spring Security CORS integration; never use `Access-Control-Allow-Origin: *` with credentialed requests. CORS **does not replace authorization** and does not prevent curl or server-to-server clients from calling the API.

When the API uses cookie authentication, the frontend must handle `credentials`/SameSite/Secure and CSRF policy. When the API uses Bearer tokens, the frontend must send `Authorization` properly, catch 401 to prompt login/refresh tokens per policy, and catch 403 to display insufficient permissions; **never retry infinitely**.

## 14. How Should an API Client Handle 401, 403, and Redirects?

Frontend pseudo-code:

```javascript
async function loadAdminData() {
  const response = await fetch("/api/admin", {
    headers: { "Accept": "application/json" },
    redirect: "manual"
  });

  if (response.status === 401) {
    // User needs to re-authenticate or credentials expired.
    // Do not loop token refreshes infinitely.
    return { action: "AUTHENTICATE" };
  }

  if (response.status === 403) {
    // Insufficient permission; inform user without auto-retrying login.
    return { action: "SHOW_FORBIDDEN" };
  }

  if (response.status >= 300 && response.status < 400) {
    // APIs should generally not send HTML login redirects.
    return { action: "UNEXPECTED_REDIRECT" };
  }

  if (!response.ok) {
    return { action: "HANDLE_OTHER_HTTP_ERROR" };
  }

  return await response.json();
}
```

This is an **illustrative logic example**, not complete production frontend code; the Basic endpoint in the lab requires an Authorization header or matching browser credentials, and cross-origin `redirect: "manual"` has Fetch/CORS limitations. In an SPA, never map every 403 to “log in again”, because the user may already have a valid login yet lack permission, and re-logging in will not fix it.

For requests expecting a JSON error body, check `Content-Type` before parsing; do not assume every 401/403 contains JSON. Successful authentication also depends on cookie/token refresh, expiration, and account state. Default retry handling should include appropriate limits, timeouts, and circuit breakers.

## 15. Security and Edge-Case Scenarios

### 15.1. 404 Can Be an Existence-Hiding Policy

Someone not allowed to view `/documents/123` is sometimes given **404** to avoid confirming document 123 exists. This **does not mean authorization is omitted**; before returning data, owner/tenant checks must still run. Policies for 403 vs 404 must be consistent across REST endpoints and logs, without creating side channels distinguishable by timing or error messages.

### 15.2. Missing Permissions After Login Because Roles/Authorities Changed

If roles change in the database while a user holds an older session, the security context may retain older authorities until refresh/re-login or synchronization runs. Before asking the user to repeatedly log in, verify effective permissions and cache/session policies. With self-contained JWTs, older tokens reflect permissions at issuance time; the server needs appropriate TTL/revocation/policy mechanisms.

### 15.3. 403 Error Even Though the User Was “Assigned ADMIN”

Spring Security `hasRole("ADMIN")` looks for authority `ROLE_ADMIN` by default. If the application stores `ADMIN` without the prefix, the check will not match. Conversely, `hasAuthority("ADMIN")` requires the exact `ADMIN` authority. Inspect the exact `GrantedAuthority` instances built from your IdP, database, and JWT scope/role converters.

With method security:

```java
@PreAuthorize("hasRole('ADMIN')")
public Report downloadInternalReport() {
    // ...
}
```

This is an illustrative snippet requiring `@EnableMethodSecurity` in configuration and a defined `Report` type. Do not assume URL rules alone protect operations invoked from background jobs, message consumers, or other services; place authorization at the layer matching your threat model.

### 15.4. Wrong Filter Chain Due to Matchers or Ordering

With multiple `SecurityFilterChain` beans, the **first matching chain** wins. If a catch-all chain precedes `/api/**`, API calls may receive a 302 form-login redirect instead of a 401 Basic response. If there is no fallback chain, a new route may go unprotected by Spring Security. Check `@Order`, `securityMatcher`, and the effective URLs after reverse-proxy rewrites.

### 15.5. Authenticated User Receives 403 Due to CSRF

Do not blame authorities for every 403. Verify:

- Is the request GET or POST/PUT/PATCH/DELETE?
- Are the session/cookie and CSRF token present?
- Is the token still valid after login/logout/session timeout?
- Did a custom filter read the body or alter tokens, or did a proxy strip/modify headers?
- Did the handler throw `InvalidCsrfTokenException`, `MissingCsrfTokenException`, or an authorization `AccessDeniedException`?

In tests, write **two separate cases**: an authorized-role user POSTing without CSRF to observe 403 from CSRF; and a user with a valid token lacking the role to observe 403 from authorization.

### 15.6. Use Accurate Status Codes Without Leaking Sensitive Info

401/403 responses should never include passwords, tokens, cookies, stack traces, database table names, confidential internal roles, or full authorization policy strings. Logging should capture request ID, route, auth scheme, status, and event type, yet **never** log raw Authorization headers/credentials. For Basic 401s, messages should suffice for client handling without disclosing whether an account exists.

### 15.7. HTTPS and Reverse Proxies

For Basic and form login, HTTPS is mandatory outside local dev. If TLS terminates at a proxy, configure trusted forwarded headers and network isolation so Spring knows the public scheme/host; otherwise `Location` can become HTTP/internal host, breaking `Secure`/Path cookies and causing browser login loops. **Never trust `X-Forwarded-*` headers directly from the public internet**.

## 16. Scenario-Based Diagnostic Workflow

| Symptom | First Question | How to Verify |
| --- | --- | --- |
| `GET /api/profile` returns 302 `/login` | Did the API hit the browser filter chain? | Check `@Order`, `securityMatcher("/api/**")`, entry point |
| `GET /api/profile` returns 401 | Were valid Basic/Bearer credentials sent? | Check `WWW-Authenticate`, request headers, redacted auth logs |
| `GET /api/admin` with USER returns 403 | Does the user have `ROLE_ADMIN`? | Check authorities and `hasRole`/`hasAuthority` |
| Anonymous `GET /app/private` returns 302 | Is this browser form login by design? | Check `Location: /login` |
| Login POST returns 403 | Is a CSRF token/session missing? | Inspect GET login form and POST token/cookie |
| Login succeeds yet loops back to `/login` | Is the session cookie saved/sent? | Inspect `Set-Cookie`/`Cookie`, proxy scheme/host/path |
| ADMIN role in DB yet still 403 | Does authority mapping have `ROLE_` prefix? | Review `GrantedAuthority`, principal, token scopes |
| 401 only when called from browser JS | Is there a CORS/preflight/credentials mismatch? | DevTools Network, OPTIONS, Access-Control headers |
| API client fails JSON parsing | Did it receive an HTML login page via redirect? | Disable follow-redirects, inspect initial HTTP status |
| `403` comes from Nginx/gateway | Did the request reach Spring? | Edge access logs vs backend logs by request ID |
| Nonexistent endpoint returns 401 | Did security block the route before mapping? | Authenticated request to similar URL; separate 401/404 |
| Basic API still accessible after logout | Is the client still sending Basic credentials? | Check request Authorization; session logout differs from Basic |
| Logout POST returns 403 | Was CSRF sent? | Check token, method, and filter chain |

### Release Checklist

- [ ] Protected APIs: anonymous → 401, wrong credentials → 401, valid credentials lacking permission → 403, valid permission → 2xx.
- [ ] Form-login web: anonymous on private → 302 to login; authenticated lacking permission → 403.
- [ ] POST `/login` and state-changing forms carry CSRF tokens; missing/invalid tokens are rejected.
- [ ] APIs never unexpectedly redirect to an HTML login page.
- [ ] `WWW-Authenticate` matches Basic/Bearer scheme/realm/scopes per contract.
- [ ] Fallback `SecurityFilterChain` exists; `@Order` and `securityMatcher` order are tested.
- [ ] Role prefixes, authorities, and object-level/tenant authorization are verified.
- [ ] CORS/preflight, HTTPS, proxy headers, session cookies, and OAuth redirects tested in a production-like environment.
- [ ] Tested logout/session invalidation, token expiry, disabled accounts, and credential rotation.
- [ ] Error bodies leak no secrets, and logs carry correlation IDs without credentials.
- [ ] Spring Boot/Spring Security are on a supported line with current patches, and no demo passwords are copied into production.

## 17. Self-Check Questions

**Q1.** An unlogged-in user calls `GET /api/admin`, which has `hasRole("ADMIN")`. Should it return 403 for missing role?  
**Answer:** No. Spring Security typically recognizes the caller is anonymous and invokes the entry point; for Basic that is 401, for form login a 302 redirect.

**Q2.** `reader` logs in successfully and calls `GET /api/admin` without `ROLE_ADMIN`. What is the usual status?  
**Answer:** 403 Forbidden; authentication succeeded, yet permission is insufficient.

**Q3.** Why can `curl -L` make you think an API returned 200?  
**Answer:** The client automatically followed the 302 to the login page and showed the final response (200 for the login page), not the API's initial status.

**Q4.** POST `/login` has valid username/password but no CSRF token. Does 403 prove the user lacks a role?  
**Answer:** No. The CSRF filter can reject the request before login/authorization is processed.

**Q5.** Which header should a Basic API 401 include?  
**Answer:** `WWW-Authenticate` with the appropriate Basic challenge per HTTP Basic/HTTP semantics, barring configured client/header exceptions.

**Q6.** Which authority does `hasRole("ADMIN")` look for by default?  
**Answer:** `ROLE_ADMIN`. `hasAuthority("ADMIN")` is what matches the literal string `ADMIN`.

**Q7.** If an API is stateless, can you set `SessionCreationPolicy.STATELESS` on all filter chains including browser form login?  
**Answer:** Not if the browser needs sessions to persist login state. Separate the API chain and the browser chain.

**Q8.** Are a CORS error and a 401 from the API the same error?  
**Answer:** No. CORS is a browser restriction on reading responses; 401 is an HTTP authentication response. They can occur together and obscure one another.

**Q9.** Must 403 always return 403 and never 404?  
**Answer:** No. Some APIs choose 404 to hide object existence, while still enforcing real authorization consistently.

**Q10.** When login succeeds and redirects to an HTTP/internal host, should you disable Secure cookies to stop the error?  
**Answer:** No. Fix the public HTTPS URL, trusted proxy headers, `Location`, and cookie policy; keep Secure cookies in production.

## 18. Official References and Further Study

- Spring Security 6.5 — *Security Architecture / ExceptionTranslationFilter*: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — *Authentication Architecture*: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — *HTTP Basic Authentication*: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security 6.5 — *Form Login*: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security 6.5 — *Multiple HttpSecurity / SecurityFilterChain*: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — *CSRF Protection*: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — *HTTP Bearer Token Authentication*: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html
- Spring Security — *Testing Spring MVC*: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Boot — *Spring Security*: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- RFC 9110 — *HTTP Semantics, 401 and 403*: https://www.rfc-editor.org/rfc/rfc9110#section-15.5
- RFC 6750 — *OAuth 2.0 Bearer Token Usage*: https://www.rfc-editor.org/rfc/rfc6750

**Conclusion:** Do not conflate “not logged in” with “logged in without permission”. In Spring Security, **`AuthenticationEntryPoint`** decides between 401/challenge or 302/login when authentication must start; **`AccessDeniedHandler`** handles access denials, typically 403. With CSRF, API gateways, CORS, or proxies, 403/302 can stem from other causes. Use clearly scoped filter chains, preserve CSRF/session policies, test **401 + challenge**, **403**, **302 + Location**, and 2xx branches so both web UIs and REST APIs behave accurately.