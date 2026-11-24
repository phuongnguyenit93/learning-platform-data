# authorizeHttpRequests and RequestMatcherDelegatingAuthorizationManager in Spring Security Servlet

## 1. The Big Picture: Being Authenticated Does Not Mean Being Authorized to Access

A **Spring Boot 3 / Spring Security 6 application on the Servlet stack** usually needs to answer two independent questions:

1. **Authentication:** "Who is sending the request?" — not logged in, logged in with username/password, Bearer token, session, or another mechanism?
2. **Authorization:** "Does that identity have permission to perform this request?" — do the URL, HTTP method, role, authority, ownership, and business rules allow it?

`authorizeHttpRequests` is the DSL used to define the **authorization policy for HTTP requests** in `HttpSecurity`. In the modern Servlet flow, Spring Security typically enforces that policy through **`AuthorizationFilter`** and an `AuthorizationManager<HttpServletRequest>` built from the rules.

Example:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Meaning: public URLs can be accessed without authentication; admin URLs require the ADMIN role; other APIs require authentication; remaining URLs are denied. **Order matters here**: the first rule matching the request is selected. The DSL has an internal mechanism that plays the decisive role: **`RequestMatcherDelegatingAuthorizationManager`**.

This lesson explains these two APIs at both the application level and internal workings, how to order matchers to avoid exposing endpoints, the relationship between `SecurityFilterChain` and `AuthorizationFilter`, and a runnable Java 17+ project with MockMvc to verify actual results.

## 2. Each Component in the Servlet Security Flow

An incoming request to the application typically passes through:

~~~text
Client
  |
  v
Servlet container
  |
  v
DelegatingFilterProxy
  |
  v
FilterChainProxy (springSecurityFilterChain)
  |
  | find the FIRST SecurityFilterChain whose securityMatcher matches
  v
Security filters belonging to the selected chain
  |
  +--> SecurityContextHolderFilter / authentication filters
  |       find or establish Authentication for the request
  |
  +--> ExceptionTranslationFilter
  |       translate AuthenticationException/AccessDeniedException
  |
  +--> AuthorizationFilter
          |
          v
      AuthorizationManager<HttpServletRequest>
          |
          v
      RequestMatcherDelegatingAuthorizationManager
          |
          +--> matcher #1 ? -> manager #1 decides
          +--> matcher #2 ? -> manager #2 decides
          +--> ... (only evaluates up to the first matching rule)
          |
          +--> no match? fallback rule is critical
          |
          v
       ALLOW / DENY
          |
          +--> ALLOW -> Servlet/MVC controller
          |
          +--> DENY  -> exception handling -> typically HTTP 401/403
~~~

The order of some filters may vary depending on version/configuration; the diagram focuses on the path related to HTTP authorization. In practice, **authentication has already been performed or restored** before the authorization decision; only a `permitAll()` rule can be decided without reading authentication/session.

Concepts:

| Component | Role |
| --- | --- |
| `HttpSecurity` | Builder that creates a `SecurityFilterChain` |
| `securityMatcher(...)` | Matcher that determines whether a request is routed into **that filter chain** |
| `authorizeHttpRequests(...)` | Declares authorization rules **inside the selected chain** |
| `requestMatchers(...)` | Matcher that selects a rule for one or more URLs/methods/request conditions |
| `AuthorizationManager` | Interface that decides allow/deny based on Authentication and context |
| `RequestMatcherDelegatingAuthorizationManager` | Pairs a list of `RequestMatcher -> AuthorizationManager`, choosing the first matching rule |
| `AuthorizationFilter` | Uses the manager to check the request before reaching the resource |
| `ExceptionTranslationFilter` | Converts certain security exceptions into a challenge/redirect or 403 |
| `AuthenticationEntryPoint` | Typically handles requests that are not yet authenticated and need login |
| `AccessDeniedHandler` | Typically handles users who are already authenticated but denied permission |

**Distinction note:** `RequestMatcherDelegatingAuthorizationManager` is not "a new filter" and not the place that handles login. It is the **dispatcher of authorization decisions** called by `AuthorizationFilter` when a request passes through the relevant chain.

## 3. What Does authorizeHttpRequests Declare?

The DSL typically takes the form:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/assets/**", "/health").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .requestMatchers("/reports/**").hasAuthority("report:read")
            .requestMatchers("/account/**").authenticated()
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

The snippet above is a **fragment of a `@Configuration` class**, requiring the appropriate imports and beans. A complete Maven project with all files is presented in section 9.

Commonly used options:

- `permitAll()`: allows everyone to access, including anonymous users.
- `denyAll()`: rejects access under this rule.
- `authenticated()`: requires an authenticated principal according to the framework's rules.
- `fullyAuthenticated()`: requires full authentication; excludes certain states such as remember-me.
- `anonymous()`: allows only anonymous users as recognized by Spring Security.
- `hasRole("ADMIN")`: by default requires the `ROLE_ADMIN` authority; do not pass the string `ROLE_ADMIN` to `hasRole`.
- `hasAuthority("report:read")`: matches the **exact authority string**, without automatically adding a prefix.
- `hasAnyRole("USER", "ADMIN")` / `hasAnyAuthority(...)`: accepts one of the corresponding permissions.
- `access(customAuthorizationManager)`: uses a custom `AuthorizationManager<RequestAuthorizationContext>` when the built-in DSL is not sufficient.

These rules apply to **HTTP request authorization**, do not replace `@PreAuthorize` on methods, do not replace data access policies by owner/tenant, and do not bypass the authentication provider. Just because the URL `/api/orders/**` is authenticated does not mean user A can view user B's orders.

### 3.1. hasRole vs. hasAuthority

Suppose `Authentication` has the authorities:

~~~text
ROLE_USER
report:read
~~~

Then:

| Check | Result for the authorities above |
| --- | --- |
| `hasRole("USER")` | Allowed (by default checks `ROLE_USER`) |
| `hasRole("ADMIN")` | Denied |
| `hasAuthority("ROLE_USER")` | Allowed |
| `hasAuthority("USER")` | Denied |
| `hasAuthority("report:read")` | Allowed |
| `authenticated()` | Allowed if Authentication is actually considered authenticated |

The default role prefix can be customized in the system; the explanation here follows the common policy. Do not assume every authority is a role; business scopes/permissions may use strings such as `report:read`, `order:write`, or `SCOPE_read`.

### 3.2. HTTP Method Is Also Part of the Matcher

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/articles/**").permitAll()
    .requestMatchers(HttpMethod.POST, "/api/articles").hasAuthority("article:create")
    .requestMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

This is an illustrative configuration snippet and requires importing `org.springframework.http.HttpMethod`. GET, POST, and DELETE have different policies; requests that do not match specific rules go to the fallback `anyRequest().authenticated()`.

**Important:** authorization rules do not replace CSRF protection. If a POST requires a CSRF token and the token is invalid, the request may be blocked **before** `AuthorizationFilter` checks the rule, even if the URL is `permitAll()`. Making a URL public via `authorizeHttpRequests` does not automatically make the endpoint exempt from CSRF.

## 4. How Does RequestMatcherDelegatingAuthorizationManager Work?

The class name is long, but its structure is very intuitive: "an authorization manager that delegates based on which matcher the request matches".

Conceptually, it holds an ordered list:

~~~text
Rule 1: [GET /public/**]          -> permitAll
Rule 2: [/admin/**]               -> hasRole("ADMIN")
Rule 3: [GET /api/reports/**]     -> hasAuthority("report:read")
Rule 4: [/api/**]                 -> authenticated
Rule 5: [any request]             -> denyAll
~~~

When a request arrives:

~~~http
GET /api/reports/weekly HTTP/1.1
Host: localhost:8080
~~~

The dispatcher checks matcher #1, #2, #3 in order. Matcher #3 matches, so **only manager #3** is used to decide. It does not continue to matcher #4 even though `/api/**` could also match.

Conceptual pseudo-code **not framework source code**:

~~~java
for (Rule rule : orderedRules) {
    if (rule.requestMatcher().matches(request)) {
        return rule.authorizationManager()
            .authorize(authenticationSupplier, requestContext);
    }
}
// No rule matched: do not rely on implicit behavior.
// Declare anyRequest().denyAll() or an explicit fallback.
~~~

In the real implementation, a manager may return an authorization/abstain result according to the interface contract and version. Do not use the pseudo-code above to infer that it always returns a boolean; the `AuthorizationDecision`/`AuthorizationResult` structure and API can vary across versions. What **must be remembered** is **matcher ordering and delegating to the first matching rule**.

### 4.1. Matcher and Manager Are Two Different Halves

- `RequestMatcher` decides **whether the request belongs to a given URL/method/dispatcher scope**.
- `AuthorizationManager` decides **whether the current Authentication satisfies the policy for a request in that scope**.

For example: the rule `requestMatchers("/admin/**").hasRole("ADMIN")` has matcher `/admin/**`; the manager checks the ADMIN role. If the URL matches but the user lacks permission, the request is denied **right within that rule**. It does **not** fall through to `.anyRequest().authenticated()` to be allowed simply because the user is logged in.

This is a major difference from a common misconception: "If the admin rule fails, it will try the next API or authenticated rule." **No** — "matching the matcher" and "being allowed access" are two stages of the **same selected rule**.

### 4.2. The Manager Structure Beneath the DSL

When declaring `authorizeHttpRequests`, Spring Security can build a `RequestMatcherDelegatingAuthorizationManager` with matcher/authorization-manager pairs. At runtime, `AuthorizationFilter` receives this manager and passes the request to it for checking.

Therefore `authorizeHttpRequests` is a **convenient API for configuration authors**, while `RequestMatcherDelegatingAuthorizationManager` is a **concrete implementation component of the rule evaluation strategy**.

In most applications, you **do not need to instantiate this class manually**. Using the DSL makes configuration easier to read and safer, especially when implementing URL-based authorization.

### 4.3. Can the Manager Be Built Manually?

Yes. In special situations, the builder API of `RequestMatcherDelegatingAuthorizationManager` allows registering matchers and AuthorizationManagers. A conceptual sketch:

~~~text
RequestMatcherDelegatingAuthorizationManager.builder()
    .add(adminMatcher, requireAdminManager)
    .add(apiMatcher, requireLoginManager)
    .anyRequest().denyAll()
    .build()
~~~

The snippet above **is pseudocode**, not standalone compilable Java: the matcher/manager names are placeholders describing the idea. Do not copy it as production source code. Its purpose is to clarify the **ordered rule list** structure. If a real custom manager is needed, you can use `.access(customAuthorizationManager)` in the DSL and integrate it with a tested policy service.

## 5. Rule Ordering: The Most Important Principle

### 5.1. From Specific to General

Proper configuration:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

`/admin/reports` is matched by the first rule requiring ADMIN; `/api/profile` requires authenticated; other URLs are denied.

**Configuration with privilege-exposure risk:**

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

For `GET /api/admin/users`, the `/api/**` rule matches **first** and is permitted for all (`permitAll`). The admin rule behind it is not evaluated. There is no mechanism where "a stricter rule automatically wins" in a first-match list.

Fix:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

More specific matchers should appear before broader matchers **when patterns can overlap**. You should also design URLs to minimize overlap, reducing the risk of accidentally changing permissions when editing configuration.

### 5.2. Rules Overlapping by Method

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**").hasAuthority("order:read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**").hasAuthority("order:write")
    .requestMatchers("/api/orders/**").denyAll()
    .anyRequest().denyAll()
);
~~~

Result: GET requires read permission, POST requires write permission, and other methods under orders are denied. If you placed `/api/orders/**.denyAll()` earlier, both GET and POST would be denied before reaching the specific rules.

**There is no automatic rule that "GET covers HEAD" in every matcher/configuration**; test the actual HTTP methods accepted by the application, including HEAD/OPTIONS when relevant. Preflight/CORS can be handled in a filter before authorization if configured.

### 5.3. Do Not Omit an Explicit Fallback

A final rule like `anyRequest().denyAll()` creates a policy of "if no rule allows it, deny it" (**deny by default**). For critical internal API applications, this is usually a safe posture.

In applications with many static pages/actuator/error endpoints, `denyAll` can cause functional errors if rules for valid resources are missing. The fix is not adding `anyRequest().permitAll()` unconditionally, but **listing the endpoints that need to be public** and testing thoroughly.

If you only want all remaining URLs to require login, use `anyRequest().authenticated()`. That is a different policy from `denyAll`; choose based on requirements rather than substituting arbitrarily.

### 5.4. Ordering Is Not "Permission Accumulation"

Suppose:

~~~java
.requestMatchers("/finance/**").hasRole("FINANCE")
.requestMatchers("/finance/report/**").hasAuthority("report:read")
~~~

A request `/finance/report/monthly` is selected by the `/finance/**` rule first. It does not require both the FINANCE role and the `report:read` permission; nor does failing FINANCE cause the second rule to run. If **AND** logic is needed, design a manager/policy that checks both conditions in **one rule**, or enforce authorization at the method/service layer.

## 6. securityMatcher, requestMatchers, and Multiple SecurityFilterChains

Two similarly named APIs with different scopes.

### 6.1. securityMatcher: Selecting the Filter Chain

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is a **snippet inside a `@Configuration` class**, requiring `@Bean`/`@Order` imports and related types; running it requires an application and appropriate beans. `securityMatcher("/api/**")` limits **this chain** to handling the corresponding API URLs. If a URL does not match the chain, **none of the internal rules in that chain are checked**.

If there are multiple chains, `FilterChainProxy` selects the **first matching chain** according to chain order (for example via `@Order`). Only after the chain is selected do the authorization rules of that chain run. **Chain `@Order`** is completely different from **the order of `.requestMatchers(...)` inside a chain**.

### 6.2. requestMatchers: Selecting the Authorization Rule Inside a Chain

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

These matchers do not decide whether the chain runs. They only apply after the request has already entered the chain.

Comparison:

| Concept | Question | Selection Mechanism |
| --- | --- | --- |
| `SecurityFilterChain.securityMatcher` | Which chain manages the request? | `FilterChainProxy` selects the first matching chain |
| `@Order` on chain bean | Which chain has priority? | Lower value is generally evaluated first |
| `authorizeHttpRequests().requestMatchers` | Within the chain, which rule is used? | `RequestMatcherDelegatingAuthorizationManager` selects the first matching matcher |
| `AuthorizationManager` | Is the user/request allowed under the selected rule? | Returns an allow/deny/abstain decision per contract |
| `@PreAuthorize` or policy service | Authorized to perform the action/touch specific data? | Checked at the method/business layer if enabled |

### 6.3. The Trap of Chains Without a Fallback

If all filter chains have narrow `securityMatcher` patterns and a request **does not match any chain**, the request may **bypass the Spring Security filters**, meaning none of those chains' HTTP authorization rules apply. Do not assume `anyRequest().denyAll()` inside an API chain protects URLs outside `/api/**`.

When full-application protection is needed, you usually use a **catch-all chain** ordered last or ensure the matchers cover all intended requests. Adding a fallback chain must account for static assets, actuator, error dispatcher, and the specific login mechanism.

### 6.4. web.ignoring vs. permitAll

`permitAll()` allows the request while still passing through the Spring Security filter chain and benefiting from applicable mechanisms such as security headers, CSRF handling, and security context management.

`web.ignoring()` (via `WebSecurityCustomizer`) skips the Spring Security filter chain for matching requests. This can drop protection layers you assumed were still active. For static resources, Spring Security generally recommends **preferring permitAll** if you want to retain security header behavior and avoid overly broad accidental bypasses.

## 7. AuthorizationFilter and Decision Characteristics

### 7.1. Authentication Supplier and Lazy Evaluation

In the `AuthorizationManager` model, authentication can be supplied via a `Supplier<Authentication>`. The idea is to fetch authentication details only when the policy actually needs them; for example, a `permitAll()` rule does not need to inspect the user's roles.

This can avoid unnecessary session lookups for certain public requests. However, do not confuse "permitAll" with "skip all filters" or "skip CSRF". The request still traverses the chain, and other filters may still act depending on configuration.

### 7.2. Allow, Deny, and Exception Outcomes

When `AuthorizationFilter` evaluates the manager for a request, a non-allowing decision can produce an `AccessDeniedException` or equivalent depending on the API/version. `ExceptionTranslationFilter` intercepts eligible exceptions and decides how to respond:

- If the request does not yet have valid authentication, `AuthenticationEntryPoint` typically produces **401** with HTTP Basic or redirects to the login page with form login.
- If the user is already authenticated but lacks sufficient permissions, `AccessDeniedHandler` typically produces **403 Forbidden**.
- If the CSRF token is invalid, the request may be blocked at the **CSRF filter before authorization**; do not conclude from a 403 that `RequestMatcherDelegatingAuthorizationManager` rejected the role.
- The HTTP outcome depends on the authentication mechanism, entry point, handler, and application policy. **Do not assume every denial must result in 403**.

For example, `GET /admin/dashboard` by a regular user with HTTP Basic and the right password: authentication succeeds, authorization denies, typically returning 403. Without credentials, the same URL typically leads to 401 and a `WWW-Authenticate: Basic` challenge.

### 7.3. Request Dispatch and Error Handling

Servlets have dispatcher types such as `REQUEST`, `FORWARD`, `ERROR`, and `ASYNC`. In some configurations, `AuthorizationFilter` may run on multiple dispatches and require authorization even for forward/error paths. This causes the `/error` page or forwarded views to be blocked if the fallback is too strict.

When genuinely needed, you can declare a specific rule:

~~~java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)
        .permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

This snippet requires `jakarta.servlet.DispatcherType`. **Only allow dispatcher types after evaluating the actual flow**; do not mechanically apply `permitAll` to dispatcher types if the application has bypass risks. Dispatcher-based rules must also be placed in the right order.

### 7.4. Dispatcher and Context Path

When using Spring MVC, `requestMatchers(String...)` can leverage MVC-compatible matchers depending on configuration/classpath. Path-based matchers should not be treated as absolute URL strings containing every context path/servlet path; apps configured with `server.servlet.context-path` or multiple servlets may need appropriate matchers and real testing.

If multiple servlets coexist in one application context, Spring Security may not know which servlet a pattern belongs to. Specify the matcher/servletPath explicitly when needed, rather than using an overly broad path pattern expecting it to always match as on the root MVC servlet.

## 8. Designing Safe HTTP Rules

### 8.1. Layering by Sensitivity

A starting order you can use:

~~~text
1. Dispatchers needed to serve error/forward (only if appropriate)
2. Public endpoints and assets explicitly decided
3. Sensitive/admin endpoints requiring high roles/authorities
4. Specific functional APIs requiring permissions
5. Remaining APIs requiring authenticated
6. Fallback denyAll
~~~

The order above **is not a formula to copy blindly for every project**. If assets live under `/admin/assets/**` and a public rule `/**` is too broad, routes can still be exposed. The first matching rule is what actually decides.

### 8.2. Distinguishing Authentication from Ownership

Suppose:

~~~java
.requestMatchers("/api/orders/**").authenticated()
~~~

This rule only proves the user is authenticated; it **does not prove** the user owns the order ID in the URL. If user A calls `GET /api/orders/123` while order 123 belongs to user B, service authorization or method security must check owner/tenant. Do not try to solve the entire per-ID data problem with a generic URL matcher.

You can use `@PreAuthorize` with a policy service when method security is enabled, or check inside the service against loaded/authorized data. The goal is to authorize close to the resource and never trust a `userId`/`tenantId` self-reported by the client.

### 8.3. HTTP Status Can Vary by Authentication Type

- HTTP Basic without credentials -> 401 with challenge.
- Form login without authentication -> 302 redirect to login page.
- Bearer API missing token -> 401 JSON/challenge depending on configuration.
- Authenticated user missing authority -> typically 403.
- Public `permitAll` endpoint -> accessible without authentication.
- `denyAll` -> denied per policy, though the exposed status also depends on exception translation/authentication state.

Therefore write integration tests with the **actual authentication mechanism**. Do not test form login and assume a 401 status like Basic.

## 9. Runnable Project: Spring Boot 3.3.13 / Java 17 / Spring Security 6

This example implements a single `SecurityFilterChain`. One `authorizeHttpRequests` defines five rules in order:

1. `GET /public/**` requires no login.
2. `GET /api/reports/**` requires authority `report:read`.
3. `/admin/**` requires `ROLE_ADMIN`.
4. Remaining `/api/**` require authenticated.
5. `anyRequest().denyAll()` denies unspecified URLs.

It uses **HTTP Basic** so test requests are easy to reproduce without needing an HTML login page. This is a local development demo; if using HTTP Basic on a real system, you must use HTTPS and a password management policy. Do not use demo passwords in production.

### 9.1. Directory Tree

~~~text
http-authorization-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/authorization/
    │   ├── HttpAuthorizationApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/authorization/
        └── AuthorizationRulesTests.java
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
    <artifactId>http-authorization-demo</artifactId>
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

**`src/main/java/com/example/authorization/HttpAuthorizationApplication.java`**

~~~java
package com.example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpAuthorizationApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/authorization/SecurityConfig.java`**

~~~java
package com.example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Matcher 1: public GET
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()

                // Matcher 2: narrow scope, requires specific authority
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")

                // Matcher 3: admin pages for admin only
                .requestMatchers("/admin/**").hasRole("ADMIN")

                // Matcher 4: remaining APIs require login
                .requestMatchers("/api/**").authenticated()

                // Matcher 5: deny by default
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String encoded = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoded)
                .authorities("ROLE_USER", "report:read")
                .build(),

            User.withUsername("bob")
                .password(encoded)
                .roles("USER")
                .build(),

            User.withUsername("admin")
                .password(encoded)
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Permissions description of the three users:**

| User | Authorities | What they can do in the demo |
| --- | --- | --- |
| `alice` | `ROLE_USER`, `report:read` | GET regular APIs and read reports; cannot enter admin |
| `bob` | `ROLE_USER` | GET regular APIs, cannot read reports, cannot enter admin |
| `admin` | `ROLE_ADMIN` | Enter admin and regular APIs; **does not automatically have `report:read`** |

Intentional point: **the ADMIN role does not automatically include every other authority**. If the business requires admin to also read reports, you must explicitly attach `report:read` or write a dedicated policy. Do not implicitly assume "ADMIN always has every permission" unless you have defined it that way.

**`src/main/java/com/example/authorization/DemoController.java`**

~~~java
package com.example.authorization;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/status")
    public Map<String, String> publicStatus() {
        return Map.of("status", "public-ok");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication auth) {
        return Map.of("username", auth.getName());
    }

    @GetMapping("/api/reports/weekly")
    public Map<String, String> weeklyReport() {
        return Map.of("report", "weekly-ok");
    }

    @GetMapping("/admin/dashboard")
    public Map<String, String> adminDashboard() {
        return Map.of("status", "admin-ok");
    }

    // Controller exists, but HTTP authorization denyAll rejects it.
    @GetMapping("/orphaned")
    public Map<String, String> orphaned() {
        return Map.of("status", "should-not-be-seen");
    }
}
~~~

The `/orphaned` endpoint is created intentionally to prove that having a controller **does not mean the path is allowed**. The final `denyAll` rule still blocks the request before it reaches the controller.

### 9.2. Testing with Spring Security MockMvc

**`src/test/java/com/example/authorization/AuthorizationRulesTests.java`**

~~~java
package com.example.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationRulesTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicGetRequiresNoCredentials() throws Exception {
        mvc.perform(get("/public/status"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("public-ok"));
    }

    @Test
    void protectedApiNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void normalUserCanAccessAuthenticatedApi() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("bob"));
    }

    @Test
    void reportingPermissionIsDistinctFromRole() throws Exception {
        mvc.perform(get("/api/reports/weekly")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.report").value("weekly-ok"));

        mvc.perform(get("/api/reports/weekly")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());

        // admin has ROLE_ADMIN but does not have report:read.
        mvc.perform(get("/api/reports/weekly")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminPathRequiresAdminRole() throws Exception {
        mvc.perform(get("/admin/dashboard")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin/dashboard")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("admin-ok"));
    }

    @Test
    void wrongPasswordIsNotAuthenticated() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void fallbackDeniesEvenAuthenticatedUser() throws Exception {
        mvc.perform(get("/orphaned")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Test explanation:**

- `httpBasic("user", "password")` creates HTTP Basic credentials for MockMvc; the test passes through Spring Security filters when using `@AutoConfigureMockMvc` and the security test dependency.
- Public GET needs no user -> 200.
- API missing authentication -> typically 401 with HTTP Basic.
- Logged-in user missing authority -> 403.
- `alice` with `report:read` reads the report -> 200, while `admin` is not automatically exempt from the authority check.
- `/orphaned` is blocked by `anyRequest().denyAll()` even though the MVC controller is declared.
- `@WithMockUser` is not used so we prove real BCrypt passwords are verified; here HTTP Basic is actively sent to test both authentication and authorization.

**Note on assertions**: For `MockMvc`, translating Spring Security exceptions to status codes depends on `ExceptionTranslationFilter`/`AuthenticationEntryPoint`. With the **HTTP Basic** configuration in this project, the 401/403 expectations above are the behavior to verify. If switched to form login, unauthenticated paths typically redirect, so the tests must be updated.

### 9.3. Running the Example

Create the files at their exact paths and run in the directory containing `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

**JDK 17+**, Maven, and network access for initial dependency downloads are required. The lines below are **expected results from the configuration**, not Maven/curl output measured in this document.

~~~bash
curl -i http://localhost:8080/public/status
# Expected 200, JSON {"status":"public-ok"}

curl -i http://localhost:8080/api/profile
# Expected 401 with HTTP Basic challenge

curl -i -u bob:demo-pass http://localhost:8080/api/profile
# Expected 200, JSON {"username":"bob"}

curl -i -u bob:demo-pass http://localhost:8080/api/reports/weekly
# Expected 403

curl -i -u alice:demo-pass http://localhost:8080/api/reports/weekly
# Expected 200, JSON {"report":"weekly-ok"}

curl -i -u admin:demo-pass http://localhost:8080/admin/dashboard
# Expected 200, JSON {"status":"admin-ok"}

curl -i -u admin:demo-pass http://localhost:8080/orphaned
# Expected 403 due to anyRequest().denyAll()
~~~

On Windows PowerShell, you can use `curl.exe` if PowerShell's `curl` alias does not behave like the traditional curl CLI.

**Do not deploy the demo as-is to the Internet:** the sample passwords shown in the documentation and HTTP Basic are only suitable when running over HTTPS in a real system. If you need a stateless Bearer/JWT API, choose an appropriate resource server/token infrastructure; the HTTP authorization rules still share the same matcher->manager idea, while authentication differs.

## 10. When a Custom AuthorizationManager Is Needed

Not every policy is cleanly expressed with `hasRole` or `hasAuthority`. A requirement might be:

> Only employees belonging to a verified department may view the internal dashboard, and they must also hold the report:read authority.

One way is to build an `AuthorizationManager<RequestAuthorizationContext>` used in `.access(...)`. Example **standalone snippet to understand the API**, not a complete class without declaring beans/services:

~~~java
AuthorizationManager<RequestAuthorizationContext> policy =
    (authenticationSupplier, context) -> {
        Authentication authentication = authenticationSupplier.get();

        boolean authenticated =
            authentication != null && authentication.isAuthenticated();

        boolean canRead = authentication != null &&
            authentication.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("report:read"));

        return new AuthorizationDecision(authenticated && canRead);
    };
~~~

This snippet needs imports for `Authentication`, `AuthorizationManager`, `AuthorizationDecision`, `RequestAuthorizationContext`, and the `policy` variable in an appropriate Java scope. It only illustrates the interface; production code must distinguish anonymous/remember-me according to policy rather than merely trusting `isAuthenticated()` on every token type. In particular, users supplied by an external service must have their permissions reliably verified.

Applying it in the HTTP DSL:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/internal/reports/**").access(policy)
    .anyRequest().denyAll()
)
~~~

This is also a snippet plugged into `HttpSecurity` where `policy` is already defined. **Do not use a custom manager just to rewrite `hasAuthority("report:read")`**; the built-in API is usually simpler and less error-prone. Use a custom manager when there are additional business rules requiring extra data/structures.

### 10.1. Where Should Ownership or Tenant Checks Live?

If the policy is "users may only view reports of their own tenant", you can:

- Check in the service after loading the data, ensuring the owner/tenant ID comes from a trusted source; or
- Use method security with `@EnableMethodSecurity` and `@PreAuthorize` calling a policy service; or
- Use a request-aware authorization manager if sufficient trusted context genuinely exists at the HTTP layer.

**Do not trust `tenantId`/`userId` from a query string as proof of permission**, and do not assume `authenticated()` already satisfies row-level security.

### 10.2. AuthorizationDecision Is Not an Authenticated Token

The manager **makes a decision** to allow/deny. It does not perform password verification, does not mint a trusted `Authentication` from a client-sent username, and does not write the session. Authentication must go through a properly designed provider/token verifier; the manager uses the verified identity and authorities.

## 11. Common Mistakes and Fixes

| Mistake | Impact | Fix |
| --- | --- | --- |
| Placing broad matcher `/api/**.permitAll()` before `/api/admin/**.hasRole(...)` | Exposes admin APIs | Place specific rules before broad ones; add endpoint tests |
| Thinking failing the first manager will try the next rule | Ignores first-match semantics | Understand the first matching matcher selects the manager and stops |
| Using `hasRole("ROLE_ADMIN")` instead of `hasRole("ADMIN")` | Wrong default prefix | Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` |
| Using `authenticated()` as an owner check | User A can access user B's data | Check ownership/tenant in service/method |
| Omitting `anyRequest` and relying on implicit default | Policy hard to read, changes hard to control | Define an explicit fallback |
| Setting `anyRequest().permitAll()` to cure 404/403 | May open unintended endpoints | Permit specific valid URLs |
| Confusing `securityMatcher` with `requestMatchers` | Config fails to protect the whole app | Check chain selection and rule selection separately |
| Having only an API chain `securityMatcher("/api/**")`, forgetting catch-all | Requests outside API may bypass Spring Security | Add a fallback chain or full coverage |
| Using `web.ignoring()` for sensitive resources | Skips security filters | Prefer `permitAll` for public resources |
| Thinking `permitAll()` automatically disables CSRF | Form POST can still get 403 due to CSRF | Design CSRF separately for the credential type |
| Thinking `hasAuthority("ADMIN")` equals `hasRole("ADMIN")` | Fails when actual authority is `ROLE_ADMIN` | Check exact `GrantedAuthority` |
| Testing only 200 without testing 401/403 | Misses exposed or over-protected endpoints | Write negative tests and rule-order tests |
| Using controller mapping as the sole security policy | Does not guarantee access control | Check HTTP authorization and method/service |
| Hard-coding all paths to internal context path | Matchers break after proxy/context changes | Use appropriate matchers and integration tests |

## 12. Safe Pre-Production Testing Process

A practical checklist:

1. **Build a URL + HTTP method + expected permission matrix**. Include public, account, admin, sensitive APIs, assets, error, and actuator if deployed.
2. **Read rules in exact order**: if two matchers overlap, verify which rule wins and whether that is intentional.
3. **Test anonymous access** on protected URLs; with HTTP Basic typically 401, with form login typically redirect.
4. **Test a lower-role user** hitting higher-privilege URLs: must be denied (typically 403).
5. **Test a user with the right role but missing extra authority** on authority-based rules; do not assume admin has all permissions.
6. **Test each HTTP method** accordingly, especially POST/PUT/PATCH/DELETE, not just GET.
7. **Test the fallback** with an existing controller not in any permitted route.
8. **Test static resources, `/error`, and dispatcher types** if the app uses forward/error rendering.
9. **Test CSRF/CORS separately**; avoid confusing a CSRF 403 error with an `AuthorizationManager` failure.
10. **Test multiple SecurityFilterChains** if the project has them; verify `@Order`, `securityMatcher`, the last chain, and which filter chain is selected.
11. **Test data-level permissions** in service/method: owner, tenant, order status, access time.
12. **Re-test after refactoring URLs**: changing paths/controllers must not accidentally open permissions.
13. **Safe audit/observability:** track authorization denials without logging passwords, tokens, session IDs, or excessive personal data.
14. **Evaluate deny by default** for endpoints not explicitly defined; when opening to public, there must be a deliberate decision and corresponding test.

When production has an API Gateway, reverse proxy, or ingress, do not rely solely on a single gateway layer to protect resources. The backend should enforce authorization appropriate to the trusted identity and check permission scope.

## 13. Self-Check Questions

**Question 1.** How does `authorizeHttpRequests` differ from `RequestMatcherDelegatingAuthorizationManager`?

**Answer:** `authorizeHttpRequests` is the DSL for declaring HTTP rules; `RequestMatcherDelegatingAuthorizationManager` is the dispatching mechanism of matcher->manager pairs built for evaluating rules.

**Question 2.** Are the two rules `/api/**.permitAll()` and `/api/admin/**.hasRole("ADMIN")` placed in that order safe for `/api/admin/users`?

**Answer:** No. The `/api/**` matcher comes first and matches, so the request gets `permitAll`; the later rule does not run.

**Question 3.** If the first rule matches but the user lacks permission, does it fall through to the next rule?

**Answer:** No. The rule has already been selected by matcher; that rule's authorization manager decides and does not try rules below it.

**Question 4.** Where do `securityMatcher("/api/**")` and `requestMatchers("/api/**")` differ?

**Answer:** `securityMatcher` decides whether the **`SecurityFilterChain`** processes the request; `requestMatchers` inside `authorizeHttpRequests` selects the **authorization rule** after the chain has been selected.

**Question 5.** Which authority does `hasRole("ADMIN")` check by default?

**Answer:** Usually `ROLE_ADMIN`. Do not pass `"ROLE_ADMIN"` into `hasRole` when using the default role prefix.

**Question 6.** Can an admin without `report:read` access a `hasAuthority("report:read")` rule?

**Answer:** No, unless the system has an explicit permission-expansion policy. The `ADMIN` role does not automatically include every other authority.

**Question 7.** Why is `anyRequest().denyAll()` needed?

**Answer:** It provides an explicit deny fallback for URLs not belonging to prior rules. However, valid public resources must be explicitly permitted.

**Question 8.** Why can a `@GetMapping("/orphaned")` controller still receive 403?

**Answer:** The request is rejected by `AuthorizationFilter` under the `denyAll` fallback before the controller is invoked.

**Question 9.** Does a `permitAll()` rule automatically disable CSRF?

**Answer:** No. CSRF is a separate filter/mechanism and can reject unsafe requests before authorization.

**Question 10.** How do you ensure user A cannot view user B's orders?

**Answer:** You need ownership/tenant authorization in the service/method or a policy with trusted data. `authenticated()` alone is not enough.

**Question 11.** When an unauthenticated user hits a protected URL, is the status always 403?

**Answer:** No. With HTTP Basic it is typically 401; form login may 302 to the login page. `AuthenticationEntryPoint` and the authentication type determine the response.

**Question 12.** Why shouldn't you use `web.ignoring()` instead of `permitAll()` for all public URLs?

**Answer:** Ignoring skips the security filter chain and can lose security headers/other protections; `permitAll` still goes through the chain.

**Key takeaway:** **`authorizeHttpRequests` builds an ordered list of HTTP rules. `RequestMatcherDelegatingAuthorizationManager` selects the first rule whose `RequestMatcher` matches, then delegates the decision to that rule's `AuthorizationManager`. Order specific matchers before broad ones, set an explicit fallback, verify chain selection separately, and always test both 401 and 403.**